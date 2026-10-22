from __future__ import annotations

import math
from typing import Any, Iterable

from .backend import LabelSpec, SchematicBackend
from .sexpr import read_sexpr_forms


def _direction_from_bbox(
    x: float,
    y: float,
    min_x: float,
    min_y: float,
    max_x: float,
    max_y: float,
) -> tuple[float, float]:
    distances = {
        "left": x - min_x,
        "right": max_x - x,
        "up": y - min_y,
        "down": max_y - y,
    }
    side = min(distances, key=distances.get)
    return {
        "left": (-1.0, 0.0),
        "right": (1.0, 0.0),
        "up": (0.0, -1.0),
        "down": (0.0, 1.0),
    }[side]


def _children(form: list[Any], tag: str) -> Iterable[list[Any]]:
    return (
        item for item in form
        if isinstance(item, list) and item and item[0] == tag
    )


def _existing_wire_ends(root: list[Any]) -> set[tuple[float, float]]:
    points: set[tuple[float, float]] = set()
    for wire in _children(root, "wire"):
        for pts in _children(wire, "pts"):
            for xy in _children(pts, "xy"):
                if len(xy) >= 3:
                    points.add((float(xy[1]), float(xy[2])))
    return points


def _existing_labels(root: list[Any]) -> list[tuple[str, float, float]]:
    labels: list[tuple[str, float, float]] = []
    for label in _children(root, "label"):
        if len(label) < 2:
            continue
        at = next(_children(label, "at"), None)
        if at is not None and len(at) >= 3:
            labels.append((str(label[1]), float(at[1]), float(at[2])))
    return labels


def _same_point(first: tuple[float, float], second: tuple[float, float]) -> bool:
    return abs(first[0] - second[0]) < 0.0001 and abs(first[1] - second[1]) < 0.0001


def insert_net_labels(
    schematic_text: str,
    reference: str,
    pin_map: dict[str, str],
    backend: SchematicBackend,
    stub: float | None = 2.54,
    grid: float = 1.27,
    font_size: float = 1.27,
    font_face: str | None = None,
    font_thickness: float | None = None,
    bold: bool = False,
    italic: bool = False,
    net_length: float | None = None,
) -> str:
    if (stub is not None and stub <= 0) or grid <= 0 or font_size <= 0:
        raise ValueError("Stub length, grid, and font size must be positive values")
    if font_thickness is not None and font_thickness <= 0:
        raise ValueError("Font thickness must be a positive value")
    if net_length is not None and net_length <= 0:
        raise ValueError("Custom net length must be a positive value")

    placements = backend.resolve_reference_pins(reference)
    if not placements:
        raise ValueError(f"Reference '{reference}' does not have any resolved pin positions in the schematic")

    known = [pin for pin in placements if pin["number"] in pin_map]
    if not known:
        raise ValueError(f"No matching pins for reference '{reference}' were found in the CSV mapping")

    owned_numbers = {pin["number"] for pin in placements}
    missing_pins = sorted(set(pin_map) - owned_numbers)
    if missing_pins:
        print(f"Warning: CSV pins not found on {reference}: {', '.join(missing_pins)}")

    min_x = min(pin["x"] for pin in placements)
    max_x = max(pin["x"] for pin in placements)
    min_y = min(pin["y"] for pin in placements)
    max_y = max(pin["y"] for pin in placements)
    wire_ends = backend.existing_wire_ends()
    labels = backend.existing_labels()
    expected: list[tuple[tuple[float, float], tuple[float, float], str]] = []
    skipped = 0

    for pin in known:
        connection = (pin["x"], pin["y"])
        if any(_same_point(connection, endpoint) for endpoint in wire_ends):
            skipped += 1
            continue

        dx, dy = _direction_from_bbox(
            pin["x"], pin["y"], min_x, min_y, max_x, max_y
        )
        net_name = pin_map[pin["number"]]
        stub_length = (
            net_length
            if net_length is not None
            else _automatic_stub_length(net_name, stub or 0.0, font_size, grid, bold)
        )
        stub_end = (
            round((pin["x"] + dx * stub_length) / grid) * grid,
            round((pin["y"] + dy * stub_length) / grid) * grid,
        )
        if any(
            existing_name == net_name
            and math.hypot(existing_x - stub_end[0], existing_y - stub_end[1]) <= 0.01
            for existing_name, existing_x, existing_y in labels
        ):
            skipped += 1
            continue

        if dx > 0:
            label_angle, justification = 0, "right bottom"
        elif dx < 0:
            label_angle, justification = 180, "left bottom"
        elif dy < 0:
            label_angle, justification = 90, "right bottom"
        else:
            label_angle, justification = 270, "left bottom"

        backend.add_wire(connection, stub_end)
        backend.add_label(
            LabelSpec(
                name=net_name,
                position=stub_end,
                angle=label_angle,
                justification=justification,
                font_size=font_size,
                font_face=font_face,
                font_thickness=font_thickness,
                bold=bold,
                italic=italic,
            )
        )
        expected.append((connection, stub_end, net_name))
        wire_ends.add(connection)
        labels.append((net_name, stub_end[0], stub_end[1]))

    print(f"Skipped {skipped} existing pin(s).")
    if not expected:
        return schematic_text

    updated = backend.serialize()

    forms = read_sexpr_forms(updated)
    if not forms:
        raise ValueError("Self-check failed: the updated schematic could not be parsed")
    updated_root = forms[0][1]
    updated_wire_ends = _existing_wire_ends(updated_root)
    updated_labels = _existing_labels(updated_root)
    for connection, stub_end, net_name in expected:
        if not any(_same_point(connection, endpoint) for endpoint in updated_wire_ends):
            raise ValueError(f"Self-check failed: wire does not end at pin {connection}")
        if not any(
            label_name == net_name
            and math.hypot(label_x - stub_end[0], label_y - stub_end[1]) <= 0.01
            for label_name, label_x, label_y in updated_labels
        ):
            raise ValueError(f"Self-check failed: label '{net_name}' is missing at {stub_end}")
    print(f"PASS: verified {len(expected)} wire and label pair(s).")
    return updated


def _automatic_stub_length(
    net_name: str,
    minimum_stub: float,
    font_size: float,
    grid: float,
    bold: bool,
) -> float:
    """Reserve label width plus pin-number and grid-snap clearance.

    KiCad stores schematic text size and coordinates in millimetres:
    https://dev-docs.kicad.org/en/file-formats/sexpr-schematic/
    """
    bold_factor = 1.1 if bold else 1.0
    estimated_text_width = len(net_name) * font_size * 0.8 * bold_factor
    pin_number_clearance = 100 * 0.0254
    snap_clearance = grid
    unrounded_length = max(
        minimum_stub,
        estimated_text_width + pin_number_clearance + snap_clearance,
    )
    return math.ceil((unrounded_length - 1e-9) / grid) * grid
