"""
split_chapters.py

Splits long audiobook files into per-chapter MP3 files based on detected
silence gaps.

Usage:
    Drop audio files into input/, then run this script with no arguments
    (works from the VS Code "Run" play button, or `python split_chapters.py`).
    Every file in input/ is processed in one batch run.

    On success, each source file's chapters are written to
    output/<source-filename>/Chapter 1.mp3, Chapter 2.mp3, ... and the
    source file is moved into input/archive/.

    Optional CLI flags override the default tuning values:
        --min-silence-len   Minimum silence gap, in seconds, to count as a
                             chapter break. Default: 2.5
        --silence-thresh    Silence threshold in dBFS. Default: -40
        --min-chapter-len   Minimum chapter length, in seconds. Shorter
                             segments are merged into a neighboring chapter.
                             Default: 60
        --bitrate           Output MP3 bitrate. Default: 192k
        --dry-run           Detect and print chapter timestamps without
                             exporting any files. If omitted, you're prompted.
        --yes               Skip the overwrite confirmation prompt and
                             always overwrite existing output.

See context/grill-sessions/2026-08-12-audiobook-chapter-splitter.md for the
full design rationale.

v2 idea (not implemented): verify/label split points with speech-to-text
(e.g. Whisper) by transcribing a short window around each silence-detected
split and checking for a spoken "chapter N" phrase.
"""

import argparse
import functools
import shutil
import time
from pathlib import Path

print = functools.partial(print, flush=True)

import imageio_ffmpeg
from mutagen.easyid3 import EasyID3
from mutagen.id3 import ID3NoHeaderError
from mutagen.mp3 import MP3
from pydub import AudioSegment

AudioSegment.converter = imageio_ffmpeg.get_ffmpeg_exe()

# How finely to scan for silence, in milliseconds. pydub's own
# silence.detect_silence defaults to a 1ms seek_step, which means ~4.4
# million tiny slices for a 74-minute file and can take upwards of ten
# minutes with zero feedback. A 100ms step is still far finer than the
# multi-second gaps we're looking for, and finishes in well under a minute.
SILENCE_SCAN_STEP_MS = 100
PROGRESS_INTERVAL_SEC = 5

SUPPORTED_EXTENSIONS = {".mp3", ".m4a", ".wav", ".aac", ".flac"}

ROOT_DIR = Path(__file__).resolve().parent
INPUT_DIR = ROOT_DIR / "input"
ARCHIVE_DIR = INPUT_DIR / "archive"
OUTPUT_DIR = ROOT_DIR / "output"

DEFAULT_MIN_SILENCE_LEN = 2.5  # seconds
DEFAULT_SILENCE_THRESH = -40  # dBFS
DEFAULT_MIN_CHAPTER_LEN = 60  # seconds
DEFAULT_BITRATE = "192k"


def parse_args():
    parser = argparse.ArgumentParser(
        description="Split a long audiobook file into per-chapter MP3s "
        "based on silence gaps."
    )
    parser.add_argument(
        "--min-silence-len",
        type=float,
        default=DEFAULT_MIN_SILENCE_LEN,
        help="Minimum silence gap, in seconds, to count as a chapter "
        f"break (default: {DEFAULT_MIN_SILENCE_LEN})",
    )
    parser.add_argument(
        "--silence-thresh",
        type=float,
        default=DEFAULT_SILENCE_THRESH,
        help=f"Silence threshold in dBFS (default: {DEFAULT_SILENCE_THRESH})",
    )
    parser.add_argument(
        "--min-chapter-len",
        type=float,
        default=DEFAULT_MIN_CHAPTER_LEN,
        help="Minimum chapter length, in seconds. Shorter segments are "
        f"merged into a neighboring chapter (default: {DEFAULT_MIN_CHAPTER_LEN})",
    )
    parser.add_argument(
        "--bitrate",
        type=str,
        default=DEFAULT_BITRATE,
        help=f"Output MP3 bitrate (default: {DEFAULT_BITRATE})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=None,
        help="Detect and print chapter timestamps without exporting files. "
        "If omitted, you'll be prompted.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Always overwrite existing output without prompting.",
    )
    return parser.parse_args()


def prompt_yes_no(question, default=False):
    suffix = "[Y/n]" if default else "[y/N]"
    answer = input(f"{question} {suffix} ").strip().lower()
    if not answer:
        return default
    return answer in ("y", "yes")


def find_input_files():
    return sorted(
        f
        for f in INPUT_DIR.iterdir()
        if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS
    )


def scan_for_silence(audio, min_silence_len_ms, silence_thresh, log):
    """Scan audio for silent ranges, logging progress as it goes.

    This is a hand-rolled replacement for pydub's silence.detect_silence:
    same idea (walk the audio in fixed-size steps, measure loudness of each
    slice), but with a much coarser step size and periodic status updates so
    a multi-hour file doesn't look hung for ten-plus minutes.
    """
    len_audio = len(audio)
    step = SILENCE_SCAN_STEP_MS

    silent_ranges = []
    current_start = None
    start_time = time.time()
    last_report = start_time

    for pos in range(0, len_audio, step):
        chunk = audio[pos:pos + step]
        is_silent = chunk.dBFS == float("-inf") or chunk.dBFS < silence_thresh

        if is_silent:
            if current_start is None:
                current_start = pos
        else:
            if current_start is not None:
                if pos - current_start >= min_silence_len_ms:
                    silent_ranges.append((current_start, pos))
                current_start = None

        now = time.time()
        if now - last_report >= PROGRESS_INTERVAL_SEC:
            pct = pos / len_audio * 100
            log(
                f"    ...scanned {ms_to_timestamp(pos)} / {ms_to_timestamp(len_audio)} "
                f"({pct:.0f}%), {len(silent_ranges)} gap(s) found so far "
                f"[{now - start_time:.0f}s elapsed]"
            )
            last_report = now

    if current_start is not None and len_audio - current_start >= min_silence_len_ms:
        silent_ranges.append((current_start, len_audio))

    elapsed = time.time() - start_time
    log(f"  Silence scan complete in {elapsed:.0f}s: {len(silent_ranges)} gap(s) found.")
    return silent_ranges


def detect_chapter_bounds(audio, min_silence_len_ms, silence_thresh, min_chapter_len_ms, log):
    """Return a list of (start_ms, end_ms) chapter boundaries."""
    silent_ranges = scan_for_silence(audio, min_silence_len_ms, silence_thresh, log)

    if not silent_ranges:
        return [(0, len(audio))]

    split_points = [(start + end) // 2 for start, end in silent_ranges]

    bounds = []
    prev = 0
    for point in split_points:
        bounds.append((prev, point))
        prev = point
    bounds.append((prev, len(audio)))

    return merge_short_chapters(bounds, min_chapter_len_ms)


def merge_short_chapters(bounds, min_chapter_len_ms):
    """Merge segments shorter than min_chapter_len_ms into a neighboring
    chapter, so a stray in-chapter pause doesn't produce a throwaway
    micro-chapter."""
    merged = []
    current_start = bounds[0][0]
    for i, (start, end) in enumerate(bounds):
        is_last = i == len(bounds) - 1
        length = end - current_start
        if length >= min_chapter_len_ms or is_last:
            merged.append((current_start, end))
            current_start = end

    if len(merged) > 1:
        last_start, last_end = merged[-1]
        if last_end - last_start < min_chapter_len_ms:
            prev_start, _ = merged[-2]
            merged[-2] = (prev_start, last_end)
            merged.pop()

    return merged


def ms_to_timestamp(ms):
    total_seconds = ms // 1000
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def tag_chapter_file(path, chapter_num, album_title):
    try:
        tags = EasyID3(path)
    except ID3NoHeaderError:
        audio = MP3(path)
        audio.add_tags()
        audio.save()
        tags = EasyID3(path)

    tags["title"] = f"Chapter {chapter_num}"
    tags["album"] = album_title
    tags["tracknumber"] = str(chapter_num)
    tags.save()


def process_file(source_path, args):
    book_name = source_path.stem
    album_title = book_name.replace("_", " ").replace("-", " ").title()
    is_dry_run = bool(args.dry_run)
    dest_output_dir = OUTPUT_DIR / (f"{book_name} (dry run)" if is_dry_run else book_name)

    log_lines = []

    def log(msg=""):
        print(msg)
        log_lines.append(msg)

    def write_log():
        (dest_output_dir / "log.txt").write_text(
            "\n".join(log_lines) + "\n", encoding="utf-8"
        )

    if dest_output_dir.exists():
        if is_dry_run:
            # Dry-run folders only ever hold a disposable log, safe to redo
            # without asking.
            shutil.rmtree(dest_output_dir)
        else:
            overwrite = args.yes or prompt_yes_no(
                f'Output folder already exists for "{book_name}", overwrite?',
                default=False,
            )
            if not overwrite:
                print(f'  Skipping "{source_path.name}" (output already exists).')
                return
            shutil.rmtree(dest_output_dir)

    dest_output_dir.mkdir(parents=True, exist_ok=True)

    log(f'Processing "{source_path.name}"...')

    log("  Loading audio (decoding via ffmpeg)...")
    load_start = time.time()
    try:
        audio = AudioSegment.from_file(source_path)
    except Exception as exc:
        log(f'  FAILED: could not read "{source_path.name}": {exc}')
        write_log()
        return
    log(f"  Loaded in {time.time() - load_start:.0f}s.")

    log(f"  Detecting silence gaps ({len(audio) / 1000 / 60:.1f} min of audio)...")
    min_silence_len_ms = int(args.min_silence_len * 1000)
    min_chapter_len_ms = int(args.min_chapter_len * 1000)

    bounds = detect_chapter_bounds(
        audio, min_silence_len_ms, args.silence_thresh, min_chapter_len_ms, log
    )
    log(f"  {len(bounds)} chapter(s) detected.")

    if is_dry_run:
        log("  Dry run, nothing exported:")
        for i, (start, end) in enumerate(bounds, start=1):
            log(f"    Chapter {i}: {ms_to_timestamp(start)} - {ms_to_timestamp(end)}")
        write_log()
        print(f"  Log saved -> {dest_output_dir / 'log.txt'}")
        return

    try:
        for i, (start, end) in enumerate(bounds, start=1):
            chapter_audio = audio[start:end]
            chapter_path = dest_output_dir / f"Chapter {i}.mp3"
            chapter_audio.export(chapter_path, format="mp3", bitrate=args.bitrate)
            tag_chapter_file(chapter_path, i, album_title)
            duration = ms_to_timestamp(end - start)
            log(f"    Exported Chapter {i}.mp3 ({duration}) [{i}/{len(bounds)}]")

        ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source_path), str(ARCHIVE_DIR / source_path.name))

        log(f"  SUCCESS: {len(bounds)} chapter file(s) created -> {dest_output_dir}")
        write_log()

    except Exception as exc:
        log(f'  FAILED to process "{source_path.name}": {exc}')
        # Keep the log for review, but remove any partial chapter exports so
        # a retry doesn't see a stale, incomplete result.
        for partial in dest_output_dir.glob("Chapter *.mp3"):
            partial.unlink(missing_ok=True)
        write_log()


def main():
    args = parse_args()

    INPUT_DIR.mkdir(parents=True, exist_ok=True)
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    files = find_input_files()
    if not files:
        print(f"No audio files found in {INPUT_DIR}")
        return

    if args.dry_run is None:
        args.dry_run = prompt_yes_no(
            "Dry run (detect chapters, don't export)?", default=False
        )

    print(f"Found {len(files)} file(s) to process.\n")

    for source_path in files:
        process_file(source_path, args)
        print()

    print("Done.")


if __name__ == "__main__":
    main()
