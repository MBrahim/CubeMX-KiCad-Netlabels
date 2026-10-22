# Design notes and verification log

This repository follows the prompt's safest default for the KiCad port: use the file-based `.kicad_sch` S-expression workflow for KiCad 8/9/10 and leave a future schematic-editor backend seam for KiCad 11+.

## Verified assumptions

- KiCad schematics are plain text S-expressions, not a binary or hidden XML format.
- The prompt's plan to insert only new text blocks and never rewrite a whole `.kicad_sch` file is consistent with a safe design and is the default chosen here.
- A reference can be found by reading the placed `symbol` entries and the `Reference` property/instances metadata without depending on a library runtime.
- The official schematic-format documentation defines the file as S-expressions, describes the top-level sections, and defines coordinates in millimetres without exponent notation: [schematic format](https://dev-docs.kicad.org/en/file-formats/sexpr-schematic/) and [common S-expression syntax](https://dev-docs.kicad.org/en/file-formats/sexpr-intro/).

## Verified against the KiCad 10 STM32F1 fixture

The fixture `tests/fixtures/STM32F1.kicad_sch` is saved by KiCad 10.0 and has an unrotated, unmirrored U1 at `(140.97, 101.6)`. The embedded library symbol places pin 14 (PA4) at local `(17.78, 22.86)` and pin 15 (PA5) at `(17.78, 20.32)`. The rendered/saved schematic uses the library's positive-Y-up coordinates as decreasing sheet Y, so the corresponding sheet points are `(158.75, 78.74)` and `(158.75, 81.28)`.

The first implementation omitted this Y inversion and computed stub sides from only the requested CSV pins. For pins 14 and 15, the latter made every bounding-box distance tie, choosing the left side and putting the labels toward/inside the symbol. The implementation now transforms the whole symbol unit's pins, inverts library Y for sheet coordinates, computes the bounds from all unit pins, and sends these right-edge pins outward to the right. The regression tests assert the exact connection and stub points.

The writer now inserts only at a top-level trailing section, reparses the result, checks each generated wire endpoint and label anchor, and skips existing wire connections on a second run. In-place writes make a timestamped backup and use a same-directory atomic replacement.

KiCad labels are anchored at the wire endpoint. The horizontal labels intentionally use inward-facing justification to place their text toward the symbol interior: right-facing 0-degree labels use `right bottom`, and left-facing 180-degree labels use `left bottom`. Auto fit adds estimated text width, pin-number clearance, and grid-snap clearance to the wire before placing the label, preserving this visual behavior while reducing pin-number overlap. The text-width estimate is approximate, so exact clearance is not guaranteed for every font; custom stub lengths can still overlap pin-number graphics.

## Phase 2 GUI

- Ported the existing card-based GUI layout and interaction pattern to KiCad controls: CSV/input/output selection, editable reference picker, CSV column/fallbacks, grid/net-length/font-size/font-thickness in mils, text style, activity log, themes, saved settings, output-folder action, and zoomable SVG preview.
- The GUI runs `python -u -m cubemx_kicad_netlabels` through `QProcess`, streams both output channels, and stops active child processes when the window closes. It writes a new output file rather than providing an in-place control.
- PySide6 is an optional GUI extra; the core CLI remains standard-library-only.
- The official [common S-expression syntax documentation](https://dev-docs.kicad.org/en/file-formats/sexpr-intro/) defines font thickness as an optional numeric token. The tool omits `(thickness ...)` for automatic/default thickness and writes an explicit thickness only when supplied. The CLI and GUI accept dimensions in mils; the CLI converts to millimetres before emitting KiCad coordinates and font values.
- The Altium-style Auto fit mode estimates text width as 0.8 font-size units per character, applies a 10% allowance for bold text, adds 100 mil for pin-number clearance plus one grid interval for endpoint-snap loss, uses `--stub` as a minimum length (300 mils by default), and rounds the endpoint to the selected grid. This leaves clearance when inward-justified text extends back toward the symbol. Custom net length uses `--net-length` and also snaps the endpoint to the grid. Grid defaults to 100 mils. Exact glyph metrics vary by font and are not parsed from KiCad; this estimate is approximate.
- KiCad 10.0 CLI SVG export completed successfully for an auto-fit output generated from `examples/pinout_example.csv` and `tests/fixtures/STM32F1.kicad_sch`. This verifies that KiCad accepts the generated schematic; the export check does not guarantee pixel-perfect text clearance for fonts whose glyph metrics differ from the estimate.
- The GUI font list begins with `Default Font` (omit a face override) and `KiCad Font`, followed by installed system fonts.
- The official [KiCad 10 CLI documentation](https://docs.kicad.org/10.0/en/cli/cli.html) documents `kicad-cli sch export svg [--output OUTPUT_DIR] ... INPUT_FILE`. On this Windows environment, KiCad 10.0.0 is installed at `C:\Program Files\KiCad\10.0\bin\kicad-cli.exe` but is not on `PATH`. The GUI's conventional-install lookup finds it, and SVG export succeeded against `tests/fixtures/STM32F1.kicad_sch`. Missing or failed exports are surfaced in the activity log and do not misreport schematic generation as failed.
- The same official S-expression documentation supports optional text font face and bold/italic style effects, which are emitted by the GUI's font controls.

## Phase 3 PCM add-on

- The official [IPC add-on developer documentation](https://dev-docs.kicad.org/en/apis-and-binding/ipc-api/for-addon-developers/index.html) states that IPC plugins are external processes, KiCad 9 and 10 expose plugin actions in the PCB Editor only, and KiCad 11 adds Schematic Editor plugin support. The implemented action scope is therefore `pcb`; this add-on does not claim a Schematic Editor action.
- The KiCad `plugin.json` schema at `https://go.kicad.org/api/schemas/v1` was fetched and used to validate the action manifest. The PCM v2 schema at `https://go.kicad.org/pcm/schemas/v2` was fetched and used to validate both archive and submission metadata. The reverse-DNS identifier is `com.github.mbrahim.cubemx-kicad-netlabels`; it satisfies the published PCM identifier pattern.
- The add-on uses KiCad's Python runtime with PySide6 and `kicad-python` in `requirements.txt`. The official `kicad-python` API exposes the open PCB via `KiCad().get_board()` and its project folder as `board.document.project.path`; the official [round-tracks example](https://gitlab.com/kicad/code/kicad-python/-/blob/main/examples/round_tracks/round_tracks_action.py) uses that same property to construct project-local paths. Its current `get_board()` implementation selects the first open PCB, not an explicitly identified active document, so the action only proceeds when exactly one PCB document is open rather than risk using the wrong project's folder. The GUI still asks the user to select the schematic, but starts that picker in the verified project folder. This does not infer that the PCB project has a particular schematic file.
- The PCB action supplies separate 24×24 `icons-light` and `icons-dark` PNGs, following the official IPC plugin schema. Both toolbar variants are generated from the user-provided artwork and included in the `plugins/` directory.
- The supplied artwork is also resized to the documented 64×64 PCM icon at `resources/icon.png`, replacing the generic add-on placeholder. The package builder checks the PNG signature and dimensions before creating the archive.
- PCM metadata is marked `testing`, uses `runtime: ipc`, and sets `kicad_version` to `10.0`, matching the only KiCad version represented by the project's real schematic fixture. The archive contains `plugins/`, optional `resources/icon.png`, and `metadata.json`; the builder computes submission hash and sizes, and keeps `download_*` values outside the archive. `jsonschema` is a packaging-time development dependency only; the core CLI remains standard-library-only.
- The action manifest sets `show-button` to `true`, requesting that KiCad show the action by default. The user reported the action may be absent on initial PCB Editor startup. Opening Preferences, selecting the add-on in the Plugins list, and clicking **OK** refreshes the toolbar and makes the action appear. KiCad's IPC plugin manager emits an internal plugin-availability event and the PCB editor handles it by recreating toolbars; no supported IPC command is exposed for an add-on to force that event. This is a KiCad-side startup/refresh limitation, not a missing `show-button` setting.
- The IPC action reports a missing PySide6 dependency with a dialog when Tk is available and otherwise writes explicit installation instructions to stderr. The official IPC documentation notes plugin output is surfaced in KiCad's warning messages as of 10.0.1.

## Phase 4 backend seam

- `SchematicBackend` in `cubemx_kicad_netlabels/backend.py` defines the contract for listing references, resolving symbol pins, querying existing wires/labels, and adding wires, labels, and no-connect markers before serialization.
- `FileBackend` implements that contract in `cubemx_kicad_netlabels/schematic.py`. It queues additions and inserts their S-expression text into the original file without reformatting existing schematic text. The CLI/writer consumes the interface rather than reaching into `FileBackend.root`.
- The writer remains the shared source for net selection, geometry, grid snapping, and generated-output checks. This phase adds no IPC implementation, IPC dependencies, or behavior/version claims; a future schematic-editor backend must implement the same contract when KiCad exposes the needed schematic IPC operations.
- The no-connect serialization uses the schematic-format `(no_connect (at X Y) (uuid ...))` form documented at [KiCad schematic file format](https://dev-docs.kicad.org/en/file-formats/sexpr-schematic/). It is covered by a parseable-output regression test.

## Open questions

- Rotation and mirror transforms are not yet verified with saved fixtures. The tool now refuses rotated or mirrored instances instead of guessing their pin coordinates. Add real KiCad-saved fixtures for all orientations before enabling these cases.
- The label angle and justification for vertical top/bottom stubs have not been validated against a KiCad-saved label. Horizontal left/right cases are tested.
- Exact backend APIs for a live schematic editor remain future work and are not implemented here.
- Command-level validation for `kicad-cli sch export netlist` and ERC checks should be confirmed against installed KiCad versions before claiming those integrations.
- Opening the generated schematic in KiCad's graphical editor still requires manual verification; the CLI SVG export was tested only with the `STM32F1.kicad_sch` fixture.
- The PCM archive and manifest schemas are validated in the build, but the action has not yet been installed and exercised in a live KiCad PCB Editor. Verify toolbar invocation, plugin-environment dependency installation, and GUI launch before promoting the metadata status from `testing`.

## Default decisions

- Core backend: file-based `.kicad_sch` editing.
- CLI: shared writer using the `SchematicBackend` contract.
- GUI: PySide6 subprocess wrapper around the CLI.
- PCM packaging: Python IPC action from the PCB Editor; selected input files are chosen in the GUI.
