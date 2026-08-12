# Audiobook Chapter Splitter

**Date:** 2026-08-12

## Purpose

Design a fully automated Python script that takes a single long MP3 (e.g. an audiobook downloaded from YouTube), splits it into per-chapter MP3 files based on silence gaps, and tags each output file with chapter metadata.
No Audacity or manual review step involved.

## Questions and Answers

**Q1: Language/runtime?**
A: Python.

**Q2: Full automation, or Audacity-assisted (generate a label track for manual review)?**
A: Fully automated.
No Audacity involvement at all.
The user is currently using Audacity's label/export-by-label workflow but wants that manual step removed since it takes a long time.
The goal is chapter metadata that shows up when the files are "picked up" (played), which in a script context means ID3 tags rather than Audacity labels.

**Q3: What should automated chapter titles be, since real chapter names aren't recoverable from audio alone?**
A: Simple sequential naming: "Chapter 1", "Chapter 2", style names.

**Q4: Silence-detection thresholds?**
A: Minimum silence length 2.5 seconds (configurable), silence threshold -40 dBFS (configurable), split at the midpoint of each detected silence gap.

**Q5: Could speech recognition detect a spoken "chapter two" as an additional/alternative split signal?**
A: Interesting but out of scope for v1.
Noted as a v2 enhancement: use Whisper (or faster-whisper) to transcribe a short window around each silence-detected split point and verify/label it against a spoken "chapter N" phrase, rather than finding splits from scratch.
Deferred due to added dependency weight, compute time, and a second failure mode.

**Q6: CLI interface / how does the script get its inputs?**
A: No required CLI args for normal use (so the VS Code play button works with zero args).
Batch mode: script processes every audio file found in an `input/` folder automatically.
For each source file, creates `output/<source-filename>/` containing the split chapter files.
On successful processing, the source file is moved into `input/archive/`.
Advanced tuning values remain available as optional CLI flags for when overrides are needed, but are not prompted for interactively.

**Q7: Guard against false splits from in-chapter pauses?**
A: Add a minimum chapter length safeguard, default 60 seconds.
Segments shorter than this after silence-based splitting get merged into the next segment.
Configurable via `--min-chapter-len`.

**Q8: Output audio bitrate?**
A: 192kbps MP3 (upgraded from an initial 128kbps suggestion), same sample rate as source.

**Q9: ffmpeg dependency handling?**
A: Bundle ffmpeg via the `imageio-ffmpeg` pip package rather than requiring a manual system install, so `pip install -r requirements.txt` is the only setup step.

**Q10: Conflict handling when re-running on a file whose output already exists?**
A: Default behavior is to overwrite: since successfully processed files get moved to archive, a file's presence back in `input/` implies the user intentionally restored it for reprocessing.
Prompt to confirm before deleting and redoing: "Output folder already exists for X, overwrite? [y/N]".

**Q11: Progress/logging and failure handling?**
A: Simple per-file status lines (processing, gaps detected, chapters exported, moved to archive).
On failure for a given file: leave the source in `input/` (don't archive it), delete any partial output folder, print a clear error, and continue on to the next file in the batch rather than aborting the whole run.

**Q12: Interactive prompt flow?**
A: Minimize prompts for the common case.
Only two prompts: dry-run y/N once per run, and overwrite-confirm per file (only when needed, from Q10).
All other tuning defaults apply silently unless overridden via CLI flags.
Album/book-title ID3 tag is auto-derived from the source filename (title-cased), no prompt.

**Q13: What if no silence gaps are found at all in a file?**
A: Still treat it as success: export the whole file as a single `Chapter 01.mp3` and move the source to archive.
Print a clear result summary at the end of each file's processing (e.g. chapter count, or "no chapters found" if applicable) so success/failure is visually obvious at a glance.

**Q14: Which input audio formats does `input/` accept?**
A: Any common format ffmpeg can decode (mp3, m4a, wav, aac, flac), always exported as MP3 chapters regardless of source format.

## Key Decisions

1. **Pure Python + pydub + ffmpeg (via imageio-ffmpeg) + mutagen** as the stack; no Audacity dependency at runtime.
   Why: removes the manual labeling/export step entirely, which was the stated goal, and keeps setup to a single `pip install -r requirements.txt`.

2. **Silence-based splitting only for v1**, with speech-recognition chapter-word detection deferred to v2.
   Why: keeps v1 shippable and testable without a heavy STT dependency; v2 can layer on as verification rather than a rewrite.

3. **Batch-folder model**: `input/` -> `output/<name>/Chapter N.mp3` -> source moved to `input/archive/` on success.
   Why: matches "drop files in, get chapters out" automation goal; makes reruns safe and idempotent by using archive-vs-input location as the signal for "already done" vs "reprocess."

4. **Minimal interactive prompts** (dry-run, overwrite-confirm only), everything else defaulted or CLI-flag-driven.
   Why: script must work unmodified from the VS Code play button (no args), so it can't require args, but also shouldn't interrogate the user on every run.

5. **Chapter titles are simple sequential names** ("Chapter 1", "Chapter 2", ...), not real book chapter titles.
   Why: real titles aren't derivable from audio without transcription/human knowledge, and the user explicitly chose full automation over accuracy here.

6. **Minimum chapter length (60s) merges spurious short segments.**
   Why: prevents an in-chapter dramatic pause from producing junk micro-files.

7. **Overwrite-by-default (with confirmation prompt) rather than skip-by-default** for already-processed files.
   Why: archive is the marker of "done"; a file's presence in `input/` means the user wants it (re)done.

8. **Continue-on-error batch processing.**
   Why: a single corrupt/unsupported file shouldn't block processing of the rest of the batch.
