# CubeMX KiCad Netlabels

> [!WARNING]
> **AI-written code.** This tool was written almost entirely by Claude | Co-Pilot, working from my design direction, feedback and bug reports. I've used and tested it on Windows with KiCad 10, but other setups are less tested, so expect rough edges. Treat it like any third-party code: keep backups of your projects and report problems in Issues.

Create KiCad schematic net labels from an STM32CubeMX pinout CSV. The app matches package pin numbers to pins on your KiCad symbol, then adds wire stubs and labels.

The original schematic can be not overwritten. The generated schematic is saved as a new file.
I recommend insepcting the generated file first then you can overwrite on the original one.

## Quick start

```bash
python -m pip install -e .
python -m cubemx_kicad_netlabels examples/pinout_example.csv tests/fixtures/simple.kicad_sch --reference U1 --dry-run
```

## GUI

Install the optional GUI dependency and launch the PySide6 application:

```bash
python -m pip install -e ".[gui]"
python -m cubemx_kicad_netlabels --gui
```

The GUI preserves the card-based layout, Dark/Light/Blue themes, remembered settings, streamed CLI log, output-folder action, and zoomable SVG preview. Its font list starts with Default Font and KiCad Font. Automatic stub length is based on the label text and rounded to the selected grid. All user-entered schematic dimensions are in mils; the CLI converts them to millimetres for KiCad's file format. The GUI writes a new `.kicad_sch` output file by default.

## CLI commands

Run these commands from the project folder after installing the package with `python -m pip install -e .`:

| Command | Description |
|---|---|
| `python -m cubemx_kicad_netlabels --gui` | Open the graphical interface. |
| `python -m cubemx_kicad_netlabels --list-references board.kicad_sch` | List placed symbol references in a schematic. |
| `python -m cubemx_kicad_netlabels --inspect board.kicad_sch --reference U1` | List pin numbers, names, and coordinates for reference `U1`. |
| `python -m cubemx_kicad_netlabels pinout.csv board.kicad_sch --reference U1 --dry-run` | Preview the selected pin-to-net labels without writing a schematic. |
| `python -m cubemx_kicad_netlabels pinout.csv board.kicad_sch --reference U1` | Generate `board_labeled.kicad_sch` beside the input schematic. |
| `python -m cubemx_kicad_netlabels pinout.csv board.kicad_sch labeled.kicad_sch --reference U1` | Generate a labeled schematic at the specified output path. |
| `python -m cubemx_kicad_netlabels pinout.csv board.kicad_sch --reference U1 --in-place` | Add labels to the input schematic after making a timestamped backup. |

Common options:

| Option | Description |
|---|---|
| `-h`, `--help` | Show all available options. |
| `--reference U1` | Choose the symbol reference to label or inspect. Default: `U1`. |
| `--column Label`, `--column Signal`, `--column Name` | Choose the CSV column used for net names. Default: `Label`. |
| `--fallback-signal` | Fall back to the CSV `Signal` value when the chosen net-name value is empty. |
| `--fallback-name` | Fall back to the CSV pin `Name` when the chosen net-name value is empty. |
| `--dry-run` | Show the selected pin-to-net labels without writing a schematic. |
| `--list-references` | List placed symbol references in the schematic path supplied as a positional argument. |
| `--inspect` | Show pin numbers, names, and coordinates for the selected `--reference`. |
| `--grid 100` | Set the endpoint snap grid in mils. Default: `100`. |
| `--stub 300` | Set the minimum wire stub length in mils for Auto fit. Default: `300`. |
| `--net-length 300`, `--net-length auto` | Use a common custom stub length in mils, or Auto fit the length to each label. Auto fit is the default. |
| `--font-size 50` | Set label text size in mils. Default: `50`. |
| `--font-face "KiCad Font"` | Set the label font face. By default, KiCad's font is used. |
| `--font-thickness 6`, `--auto-thickness` | Set explicit font thickness in mils or use KiCad's automatic thickness. Automatic thickness is the default. |
| `--bold`, `--italic` | Apply bold or italic label text. |
| `--in-place` | Write into the input schematic after creating a timestamped `.bak` backup. |
| `--force` | Bypass the lock-file check for an in-place write; do not edit the same schematic in KiCad at the same time. |

The dimensions `--stub`, `--net-length`, `--grid`, `--font-size`, and `--font-thickness` are in mils. Without `--in-place`, the CLI writes a separate output file and never overwrites the input schematic. `--force` only applies to in-place writes.

## CSV format

Use a standard CubeMX export with the `Position,Name,Type,Signal,Label` columns.

```csv
Position,Name,Type,Signal,Label
14,PA0,I/O,ADC1_IN0,BTN_1
15,PA1,I/O,GPIO_Output,LED_RED
```

## KiCad PCB Editor add-on

The IPC add-on provides a PCB Editor toolbar action named **Label schematic from CubeMX CSV** with the supplied CubeMX/KiCad artwork in light and dark themes. The same artwork is included as the PCM package icon (`resources/icon.png`, 64×64), replacing the generic package placeholder. The action opens the GUI, where you choose the CSV and schematic files; both file pickers start in the current PCB's project folder. To avoid guessing when more than one PCB document is open, the action requires exactly one open PCB. The bundled GUI needs PySide6, and the action uses `kicad-python` to read the open board's project folder. If a dependency is unavailable, the action displays installation instructions for the KiCad plugin's Python environment.

The PCM package targets the KiCad 10.0+ metadata format and is marked `testing`; the IPC action has not yet been manually exercised inside KiCad. To build a local package and the metadata for a future catalog submission:

```bash
python -m pip install -r tools/requirements.txt
python tools/build_pcm_package.py
```

The builder fetches the official KiCad PCM v2 and IPC plugin schemas and validates the package and action manifests. It writes the archive and `metadata.submit.json` under `dist/`. The archive contains `plugins/`, `resources/icon.png`, and `metadata.json`; the submission metadata includes the release URL, SHA-256, download size, and install size, and is not included in the archive. A `v*` Git tag triggers tests, package creation, and a GitHub release with both files attached. Submitting `metadata.submit.json` to the KiCad add-on metadata repository remains a maintainer action.

### Toolbar button does not appear after startup

The action manifest requests a toolbar button by default (`show-button: true`). Sometimes the action does not appear in the PCB Editor toolbar the first time KiCad starts, as reported in [KiCad issue #20706](https://gitlab.com/kicad/code/kicad/-/work_items/20706). To refresh it, open Preferences, select the add-on in the Plugins list, and click **OK**; the toolbar action should then appear. The add-on has no supported IPC command to force that KiCad-side refresh. If the problem persists, report the KiCad version with the issue.

## Notes

- The `SchematicBackend` interface separates symbol/pin reads and schematic edits (wire, label, and no-connect) from the CLI writer. `FileBackend` is the current S-expression implementation and preserves the original text while inserting serialized additions.
- A live schematic-editor IPC backend is future work for a KiCad version that exposes that editor through IPC. No IPC schematic backend or KiCad 11 support is implemented or claimed.
- Only the unrotated, unmirrored KiCad 10.0 fixture has been checked. Rotated and mirrored symbols are rejected until their transforms are verified against real fixtures.
- The file-based backend is designed for use with KiCad-saved `.kicad_sch` files. KiCad 8 and 9 compatibility has not been fixture-tested, and no support claim is made for those versions.
- Reload the generated schematic in KiCad (File → Reload), then check that labels are outside the symbol, attached to the correct pins, and do not introduce ERC errors.
- The implementation is intentionally conservative: unverified format decisions and remaining limitations are documented in `docs/DESIGN.md`.

## Development

```bash
pytest
```
