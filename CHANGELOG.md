# Changelog

## 1.3.0 – 2026-10-10
- Standalone desktop app for macOS and Windows (own window, no Python or browser needed): `desktop/app.py`
  with pywebview, packaged by PyInstaller (`desktop/keygroup_creator.spec`) and built automatically on GitHub
  for every release (`.github/workflows/build-apps.yml`).
- Folder and template choosers use the window's native dialogs in the desktop app.
- Preset names and confirmations use in-page dialogs (the desktop window has no browser prompt/confirm).
- MIT license.

## 1.2.0 – 2026-10-10
- Browser previews for the MPC: each program gets `[Previews]/Name.xpm.ogg` next to it, made from the sample
  closest to C3 (loudest layer), up to 6 s (adjustable) with a short fade.
- Built-in Ogg Vorbis encoder (`ogg_preview.py`, pure Python): nothing to install. Checked with the libvorbis
  and ffmpeg decoders.
- Command line: `--no-preview`, `--preview-seconds`.

## 1.1.0 – 2026-10-10
- One program per instrument: a folder with several sampled instruments (Pad-C3…, Lead-C3…) is split by the
  name before the note; each instrument has its own name, sound and checkbox, and all are created at once.
  Samples without a note join the instrument whose name they start with. Turn it off to get a single program.
- Sound presets for envelopes and filter: Pad, Lead, Pluck, Keys, Bass and Strings to start with; pick one per
  instrument (suggested from the name), edit it, save it under your own name, rename or delete it, apply the
  current sound to every instrument, or restore the built-in ones. Saved in `presets.json`.
- Command line: `--split` and `--preset NAME|auto`.
- The program name is now edited in the instrument list.

## 1.0.3 – 2026-10-10
- Loops in AIFF files are now read (INST sustain loop + MARK markers, as written by Logic's Auto Sampler).
- Looped samples are set up like the MPC does: the sample ends at the loop end and loops forward from the loop start
  (before, the end was the end of the file). WAV `smpl` loop ends are used too.
- New "Loop" column in the sample table and an option (`--no-loops`) to ignore the stored loops.

## 1.0.2 – 2026-10-10
- Filter 1 ↔ 2 mix control, starting at 0 (only filter 1). The MPC default of 50 mixed both filters.
- Option to run the filters in series instead of parallel.

## 1.0.1 – 2026-10-10
- Samples now go in `Name_[ProgramData]/` next to `Name.xpm`, the layout MPC 3.x uses; the `.xpm` is saved directly in the chosen folder.
- Removed the "create a folder with the program name" option (and `--no-subfolder`).

## 1.0.0 – 2026-10-10
- First version: one MPC 3.x keygroup program per run from a folder of samples.
- Root note and velocity read from file names (C3 = 60 or C4 = 60), with fallback to the note stored in WAV/AIFF.
- Up to 8 velocity layers (top / center / equal parts), zones centered, at the bottom or at the top, optional stretch to 0–127.
- Amp envelope, filter (type, cutoff, resonance, env amount, key track, velocity) and filter envelope.
- Browser interface (English/Spanish) with editable sample table, key map, sample preview; macOS app builder; command line.
