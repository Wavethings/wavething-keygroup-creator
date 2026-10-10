# Wavethings Keygroup Creator

Builds an **MPC 3.x keygroup program** (`.xpm`) from a folder of samples whose names carry the root
note — and optionally the velocity layer — with amp envelope, filter and filter envelope set in the
same app. Only Python 3.9+ is needed, nothing to install.

*Crea un **programa keygroup de MPC 3.x** (`.xpm`) a partir de una carpeta de samples cuyos nombres
llevan la nota raíz (y, si quieres, la capa de velocidad), con envolvente, filtro y envolvente de filtro
en la misma app. Solo necesita Python 3.9+.*

## Download the app / Descargar la app
Go to this project's **[Releases page](../../releases)**, download `Wavethings-Keygroup-Creator-macOS.zip` or
`Wavethings-Keygroup-Creator-Windows.zip`, unzip it and open the app. It has its own window: no Python, no
browser, no Terminal. *Descarga el ZIP de tu sistema en la página de Releases, descomprímelo y abre la app.*

The app is not signed with a paid Apple/Microsoft developer certificate, so the first time:
- **macOS:** double-click it; when macOS refuses, go to **System Settings → Privacy & Security** and click
  **Open Anyway** (on older macOS: right-click the app → **Open**). After that it opens normally.
  The macOS build is for Apple Silicon (M1 or newer).
- **Windows:** SmartScreen says "Windows protected your PC" → **More info** → **Run anyway**. Keep the
  `.exe` inside its folder (the folder holds the files it needs). Needs Windows 10 or 11.

## Run from source / Desde el código
### Lighter macOS app (opens in your browser)
    python3 build_app.py
Drag `Wavethings Keygroup Creator.app` to Applications. It quits when you close the browser tab.
Settings live in `~/Library/Application Support/Wavethings Keygroup Creator/` (with a `log.txt`).

### Command line
    python3 mpc_keygroup_creator.py ~/Samples/MyLead -o ~/MPC/Programs --list      # only show the map
    python3 mpc_keygroup_creator.py ~/Samples/Logic -o ~/MPC/Programs --split --preset auto   # one per instrument
    python3 mpc_keygroup_creator.py ~/Samples/MyLead -o ~/MPC/Programs \
        --amp 0,0,40,80,30 --filter 3,60,15,40 --fenv 0,0,50,0,30
`-h` shows every option.

## Names it understands / Nombres que entiende
| In the name | Meaning |
|---|---|
| `C2`, `F#3`, `Db4`, `Cs3`, `A-1` | root note (the last one in the name). C3 = 60 like the MPC; switch to C4 = 60 if your pack uses it |
| `V127`, `v64`, `vel100`, `Velocity 90` | velocity layer |
| `v1 v2 v3…` | layer numbers → the 0–127 range split in equal parts |
| `pp p mp mf f ff fff` | dynamics, softest to loudest |
| `_060_` (optional) | MIDI note number |
If the name has no note, the root stored inside the WAV (`smpl`) or AIFF (`INST`) is used.

Velocity values become ranges: by default each value is the **top** of its range
(V40, V90, V127 → 0–40, 41–90, 91–127). "Center" and "Equal parts" are also available. If one layer is
missing a note, that keygroup borrows the nearest sample of the same layer. Up to 8 layers and 128 keygroups.

## Where the samples go / Dónde van los samples
Same layout MPC 3.x uses when it saves a program: `Name.xpm` goes in the folder you choose, its
samples are copied (or hard-linked) into `Name_[ProgramData]/` next to it, and the preview goes in `[Previews]/`. The `.xpm` stores only each
sample's file name, as the MPC does. Copy the `.xpm` and its `_[ProgramData]` folder together.

*Igual que la MPC 3.x: `Nombre.xpm` en la carpeta elegida y los samples en `Nombre_[ProgramData]/` a su lado.*

## Browser previews / Preescuchas
Each program also gets `[Previews]/Name.xpm.ogg`, which the MPC browser plays when the program is selected.
It uses the sample closest to C3 (loudest layer), up to 6 seconds with a short fade out. The Ogg Vorbis file is
written by a small encoder included in the app (`ogg_preview.py`), so ffmpeg or other tools are not needed;
it is tuned for previews (about 150 kbps), not for archiving audio.

## Sound presets / Presets de sonido
Presets are saved in `presets.json` in the settings folder, shared by the app and the command line. The built-in
values are rough starting points, not measured on an MPC — check them there and save your own versions.
*Restore built-in presets* puts the originals back without touching yours.

## Template
The built-in template is a keygroup saved by MPC 3.9. *Use another .xpm…* lets you pick any keygroup
saved by your MPC (with your favourite FX, mod settings…): everything is kept except the keygroups,
samples and the envelope/filter values you set.

## Notes
- Filter mix starts at 0 (only filter 1 is heard; the MPC default 50 mixes both). Filters can run in series (`--serial`).
- Filter types 0–18 and 29 are named; any other index can be typed in.
- Loop points stored in the samples (WAV `smpl`, AIFF `INST`/`MARK` as Logic's Auto Sampler writes them) are carried over: like the MPC, the sample ends at the loop end and loops forward from the loop start.
- Tests: `python3 -m unittest discover -s tests`

## Publishing a new version (maintainers)
The desktop apps are built by `.github/workflows/build-apps.yml` on GitHub's own macOS and Windows machines:
publish a **Release** on GitHub (tag like `v1.3.0`) and, a few minutes later, the two ZIP files appear attached
to it. To try a build without publishing, open **Actions → build desktop apps → Run workflow**; the ZIPs show up
under *Artifacts* of that run. To build locally instead: `pip install -r requirements-desktop.txt pyinstaller`,
`python3 scripts/make_desktop_icons.py`, `pyinstaller desktop/keygroup_creator.spec --noconfirm`.

## License
MIT, see `LICENSE`.
