# Audiobook Chapter Splitter

This tool takes one long audio file (like an audiobook downloaded as a single MP3) and automatically splits it into separate chapter files.
It listens for the quiet pauses between chapters and cuts the file there, so you don't have to do it by hand.

## What you need before starting

1. **Python** installed on your computer.
   If you're not sure whether you have it, open a terminal (see below) and type `python --version`.
   If that shows a version number, you're good.
   If not, download it from [python.org](https://www.python.org/downloads/) and install it.
2. This project folder, downloaded onto your computer.
3. **VS Code** (recommended) or any terminal you're comfortable with.

## One-time setup

You only need to do this once.

1. Open this project folder in VS Code.
2. Open a terminal inside VS Code.
   You can do this from the menu: **Terminal > New Terminal**.
3. In that terminal, type the following and press Enter:

   ```
   pip install -r requirements.txt
   ```

4. Wait for it to finish.
   It downloads a few small helper programs the script needs.
   You'll see some text scroll by, and it's done when you get your cursor back with no red error text.

## Everyday use

Here's the normal workflow every time you have a new audiobook to split.

### 1. Drop your audio file into the `input` folder

Find the `input` folder inside this project.
Drag and drop your audio file into it (MP3, M4A, WAV, AAC, and FLAC all work).
You can drop in more than one file at a time if you have several books to process.

### 2. Run the script

In VS Code, open the file `split_chapters.py`.
Then click the **Run** (play) button in the top-right corner of the window.

A panel will open at the bottom asking you questions.
For normal use, just answer:

- **"Dry run (detect chapters, don't export)?"** → type `n` and press Enter (or just press Enter, since "no" is the default).
- If it asks about overwriting an existing folder, only answer `y` if you actually want to redo that book.

### 3. Wait for it to finish

The script prints what it's doing as it goes, so you can watch its progress:

- Loading the audio file.
- Scanning for quiet gaps (this is the part that takes the longest on a long book).
- Exporting each chapter, one at a time.

A typical audiobook takes somewhere around a minute or two total.

### 4. Find your chapters

Look inside the `output` folder.
You'll find a new folder named after your book, containing files like `Chapter 1.mp3`, `Chapter 2.mp3`, and so on.

Your original file will no longer be in `input`.
It gets moved automatically into `input/archive` once it's done, so you know it's already been processed.

## "Dry run" mode: previewing before you commit

If you want to see how many chapters the script *would* create, without actually creating any files, answer `y` (yes) to the dry run question instead.

This is useful if a book's chapters seem off (too many or too few) and you want to experiment with the settings below before doing the real thing.

A dry run still saves a log file, in a folder named like `output/My Book (dry run)/log.txt`, so you can review exactly what it found.

## If the chapter count looks wrong

Every book is narrated a little differently, so the default settings won't be perfect for every audiobook.
If you know the real chapter count (for example, by looking the book up online) and the script found a very different number, you can nudge it with an extra setting.

In the terminal, instead of clicking the Run button, type a command like this:

```
python split_chapters.py --min-chapter-len 30
```

That number is the shortest a chapter is allowed to be, in seconds, before the script merges it into a neighboring chapter.

- If the script is creating **too many** short, choppy files, try a **higher** number (e.g. `60` or `90`).
- If the script is **combining** what should be separate chapters, try a **lower** number (e.g. `20` or `30`).

You can combine this with `--dry-run` to test settings without exporting anything:

```
python split_chapters.py --dry-run --min-chapter-len 30
```

## Folder overview

```
input/            Drop your audio files here
input/archive/    Successfully processed files end up here automatically
output/           Your finished chapter files appear here, one folder per book
```

## Troubleshooting

- **"No audio files found in input"**: make sure your file is actually inside the `input` folder, not a subfolder, and that it's one of the supported formats (MP3, M4A, WAV, AAC, FLAC).
- **A file failed partway through**: check the `log.txt` file inside its folder in `output` for details.
  Your original file stays safely in `input` (it only moves to `input/archive` on success), so it's safe to try again.
- **Still stuck**: reach out to whoever set this up for you.
