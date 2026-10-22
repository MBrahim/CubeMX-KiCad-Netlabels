# Changelog

## 1.0.0

- Start both PCB Editor file pickers in the currently open board's KiCad project folder.
- Document the toolbar refresh workaround: select the add-on in Preferences and click OK.
- Initial project scaffold and CSV + S-expression utilities.
- Added a KiCad schematic backend abstraction and a file-based backend.
- Added basic pytest coverage for CSV parsing and S-expression reading.
- Fixed pin Y-coordinate conversion and stub direction using the full symbol-unit pin bounds, verified against the KiCad 10.0 STM32F1 fixture.
- Added generated-output self-checks, idempotent wire detection, atomic writes, and timestamped backups for `--in-place`.
- Reject rotated and mirrored symbol instances until their transforms are verified against real fixtures.
- Ported the existing PySide6 GUI design to KiCad with themes, saved settings, streamed CLI output, output-folder access, and SVG preview.
- Added optional `.[gui]` dependencies, GUI launch entrypoints, reference listing for the GUI, and KiCad label font options.
- Aligned the GUI with the KiCad CLI, removed unsupported underline/strike-through and color controls, added automatic/explicit font thickness, and made CLI/GUI dimensions consistently use mils.
- Added Default Font and KiCad Font as the first GUI font choices, plus grid-rounded label-length automatic stubs in the CLI and GUI.
- Matched Altium's Auto fit/Custom net-length controls: automatic lengths use label width with a minimum stub, while custom lengths use one grid-snapped value for all labels.
- Increased Auto fit label clearance for inward-justified text to reduce overlap with pin-number graphics, while retaining grid rounding and the configured minimum stub.
- Added an experimental KiCad IPC PCB Editor action, PCM v2 package builder and metadata validation, and tag-triggered GitHub release assets.
- Added the `SchematicBackend` contract and moved serialization of wires, labels, and no-connect markers behind `FileBackend`; no schematic IPC backend is implemented.
- Added the supplied CubeMX/KiCad artwork as light/dark 24×24 toolbar icons and the 64×64 PCM package icon, replacing the generic placeholder.

## 0.1.1

- Use the supplied CubeMX/KiCad icon for the IPC toolbar action and PCM package listing.
