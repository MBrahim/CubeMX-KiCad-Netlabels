from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from .csv_input import read_cube_csv
from .schematic import FileBackend
from .writer import insert_net_labels


def _parse_stub(value: str) -> float | None:
    if value.casefold() == "auto":
        return None
    try:
        stub_mils = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "stub must be a positive number of mils or 'auto'"
        ) from exc
    if stub_mils <= 0:
        raise argparse.ArgumentTypeError("stub length must be positive")
    return stub_mils


def _write_atomically(output: Path, content: bytes, preserve_metadata_from: Path | None = None) -> None:
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{output.name}.", suffix=".tmp", dir=output.parent)
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        if preserve_metadata_from is not None:
            shutil.copystat(preserve_metadata_from, temporary_path)
        os.replace(temporary_path, output)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create KiCad net labels from a CubeMX pinout CSV.")
    parser.add_argument("csv", nargs="?", help="CubeMX CSV exported from STM32CubeMX")
    parser.add_argument("schematic", nargs="?", help="Input KiCad schematic (.kicad_sch)")
    parser.add_argument("output", nargs="?", help="Output schematic (.kicad_sch) to write")
    parser.add_argument("--reference", default="U1", help="Reference to label, e.g. U1")
    parser.add_argument("--column", choices=["Label", "Signal", "Name"], default="Label")
    parser.add_argument("--fallback-signal", action="store_true")
    parser.add_argument("--fallback-name", action="store_true")
    parser.add_argument("--list-references", action="store_true", help="List placed references in the schematic")
    parser.add_argument("--inspect", action="store_true", help="Inspect the pins for the chosen reference")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--in-place", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--gui", action="store_true", help="Launch the PySide6 GUI")
    parser.add_argument("--stub",type=_parse_stub, default=300.0,help="Minimum wire stub length for Auto fit, in mils (default: 300)")
    parser.add_argument("--net-length", type=_parse_stub, default=None, help="Custom wire stub length in mils; omit or use 'auto' for Auto fit")
    parser.add_argument("--grid", type=float, default=100.0, help="Schematic grid in mils")
    parser.add_argument("--font-size", type=float, default=50.0, help="Label font size in mils")
    parser.add_argument("--font-face", help="Label TrueType font face")
    parser.add_argument("--font-thickness", type=float, help="Explicit label font thickness in mils (omitted for automatic thickness)")
    parser.add_argument("--auto-thickness", action="store_true", help="Use KiCad's automatic font thickness (the default)")
    parser.add_argument("--bold", action="store_true", help="Use bold label text")
    parser.add_argument("--italic", action="store_true", help="Use italic label text")
    parser.add_argument("--mark-unused-pins", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    raw_args = list(sys.argv[1:] if argv is None else argv)
    if "--gui" in raw_args:
        try:
            from .gui import launch
        except ImportError as exc:
            print(
                "The GUI requires PySide6. Install it with "
                "'python -m pip install -e \".[gui]\"'.",
                file=sys.stderr,
            )
            print(f"GUI import error: {exc}", file=sys.stderr)
            return 1
        return launch()

    parser = _build_parser()
    args = parser.parse_args(raw_args)

    try:
        if args.list_references:
            schematic_path = args.schematic or args.csv
            if not schematic_path:
                parser.error("--list-references requires a schematic path")
            backend = FileBackend(schematic_path)
            for ref in backend.list_references():
                print(ref)
            return 0

        if args.inspect:
            schematic_path = args.schematic or args.csv
            if not schematic_path:
                parser.error("--inspect requires a schematic path")
            backend = FileBackend(schematic_path)
            for pin in backend.resolve_reference_pins(args.reference):
                x_mils = pin["x"] * 1000 / 25.4
                y_mils = pin["y"] * 1000 / 25.4
                print(
                    f"{pin['number']}: {pin['name']} "
                    f"@ ({x_mils:.2f}, {y_mils:.2f}) mils"
                )
            return 0
        if not args.schematic:
            parser.error("a schematic path is required")
        backend = FileBackend(args.schematic)

        if not args.csv:
            parser.error("a CubeMX CSV path is required")
        nets = read_cube_csv(args.csv, column=args.column, fallback_signal=args.fallback_signal, fallback_name=args.fallback_name)
        refs = backend.list_references()
        if not refs:
            print("No placed symbols found in the schematic.")
            return 1
        if args.reference.lower() not in {ref.lower() for ref in refs}:
            print(f"Reference '{args.reference}' was not found in the schematic. Available: {', '.join(refs)}")
            return 1

        input_path = Path(args.schematic)
        output = Path(args.output) if args.output else input_path.with_name(f"{input_path.stem}_labeled.kicad_sch")
        if args.in_place:
            output = input_path
        if output.resolve() == input_path.resolve() and not args.in_place:
            print("Refusing to overwrite the input schematic without --in-place.")
            return 1

        if args.dry_run:
            print(f"Dry run for {args.reference}: {len(nets)} labels selected")
            for pin, net in sorted(nets.items()):
                print(f"  pin {pin}: {net}")
            return 0

        lock_paths = (
            input_path.with_name(f"~{input_path.name}.lck"),
            input_path.with_name(f"{input_path.name}.lck"),
        )
        if args.in_place and not args.force and any(lock.exists() for lock in lock_paths):
            print("Lock file detected; use --force to overwrite.")
            return 1

        original_bytes = input_path.read_bytes()
        has_utf8_bom = original_bytes.startswith(b"\xef\xbb\xbf")
        source = original_bytes.decode("utf-8-sig")
        if args.font_thickness is not None and args.font_thickness <= 0:
            parser.error("--font-thickness must be positive")
        if args.auto_thickness and args.font_thickness is not None:
            parser.error("--auto-thickness and --font-thickness cannot be used together")
        mil_to_mm = 0.0254
        updated = insert_net_labels(
            source,
            args.reference,
            nets,
            backend,
            stub=args.stub * mil_to_mm if args.stub is not None else 300 * mil_to_mm,
            grid=args.grid * mil_to_mm,
            font_size=args.font_size * mil_to_mm,
            font_face=args.font_face,
            font_thickness=(
                args.font_thickness * mil_to_mm
                if args.font_thickness is not None else None
            ),
            bold=args.bold,
            italic=args.italic,
            net_length=(
                args.net_length * mil_to_mm
                if args.net_length is not None else None
            ),
        )
        if updated == source:
            print("No new labels were inserted; all matching pins already have wires or labels.")
            return 0
        if args.in_place:
            backup_path = input_path.with_name(
                f"{input_path.name}.{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}.bak"
            )
            shutil.copy2(input_path, backup_path)
            print(f"Backup: {backup_path}")
        output_bytes = (b"\xef\xbb\xbf" if has_utf8_bom else b"") + updated.encode("utf-8")
        _write_atomically(output, output_bytes, input_path if args.in_place else None)
        print(f"Wrote '{output}'")
        print("Reload the schematic in KiCad (File -> Reload).")
        return 0
    except SystemExit:
        raise
    except Exception as exc:  # pragma: no cover - CLI surface
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
