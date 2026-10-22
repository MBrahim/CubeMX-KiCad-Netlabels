from __future__ import annotations

from pathlib import Path
import uuid
from typing import Any, Iterable, Optional, Sequence

from .backend import LabelSpec, PinPlacement, PinRecord, Point, SchematicBackend
from .sexpr import read_sexpr_forms


class FileBackend(SchematicBackend):
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.text = self.path.read_bytes().decode("utf-8-sig")
        self.root = self._parse_root()
        self.lib_symbols = self._collect_lib_symbols()
        self._pending_forms: list[str] = []
        self._pending_wire_ends: set[Point] = set()
        self._pending_labels: list[tuple[str, float, float]] = []

    def _parse_root(self):
        forms = read_sexpr_forms(self.text)
        if not forms:
            raise ValueError(f"{self.path} does not contain a valid S-expression")
        return forms[0][1]

    def _collect_lib_symbols(self):
        for item in self.root:
            if isinstance(item, list) and item and item[0] == "lib_symbols":
                return item[1:]
        return []

    def list_references(self) -> list[str]:
        refs: list[str] = []
        for item in self.root:
            if isinstance(item, list) and item and item[0] == "symbol":
                ref = self._symbol_reference(item)
                if ref and ref not in refs:
                    refs.append(ref)
        return refs

    def pins_for_reference(self, reference: str) -> list[PinRecord]:
        matches: list[PinRecord] = []
        for item in self.root:
            if not isinstance(item, list) or not item or item[0] != "symbol":
                continue
            ref = self._symbol_reference(item)
            if ref is not None and ref.lower() != reference.lower():
                continue
            matches.extend(self._symbol_pins(item))
        return matches

    def resolve_reference_pins(self, reference: str) -> list[PinPlacement]:
        refs: list[PinPlacement] = []
        for item in self.root:
            if not isinstance(item, list) or not item or item[0] != "symbol":
                continue
            ref = self._symbol_reference(item)
            if ref is None or ref.lower() != reference.lower():
                continue
            lib_id = self._symbol_lib_id(item)
            placed_at = self._symbol_at(item)
            unit = self._symbol_unit(item)
            body_style = self._symbol_body_style(item)
            if placed_at[2] % 360:
                raise ValueError(
                    f"Reference '{reference}' is rotated; coordinate transforms for rotated "
                    "symbols are not yet verified."
                )
            if any(
                isinstance(entry, list) and entry and entry[0] == "mirror"
                for entry in item
            ):
                raise ValueError(
                    f"Reference '{reference}' is mirrored; coordinate transforms for mirrored "
                    "symbols are not yet verified."
                )
            for pin in self._library_pins_for_instance(lib_id, unit, body_style):
                local_x = pin["x"]
                local_y = -pin["y"]
                refs.append({
                    "number": pin["number"],
                    "name": pin["name"],
                    "electrical": pin["electrical"],
                    "x": placed_at[0] + local_x,
                    "y": placed_at[1] + local_y,
                })
        return refs

    def existing_wire_ends(self) -> set[Point]:
        points: set[Point] = set(self._pending_wire_ends)
        for wire in self._children(self.root, "wire"):
            for pts in self._children(wire, "pts"):
                for xy in self._children(pts, "xy"):
                    if len(xy) >= 3:
                        points.add((float(xy[1]), float(xy[2])))
        return points

    def existing_labels(self) -> list[tuple[str, float, float]]:
        labels = list(self._pending_labels)
        for label in self._children(self.root, "label"):
            if len(label) < 2:
                continue
            at = next(self._children(label, "at"), None)
            if at is not None and len(at) >= 3:
                labels.append((str(label[1]), float(at[1]), float(at[2])))
        return labels

    def add_wire(self, start: Point, end: Point) -> None:
        """Queue a wire using the KiCad schematic S-expression format.

        Format: https://dev-docs.kicad.org/en/file-formats/sexpr-schematic/
        """
        indent = self._indent()
        self._pending_forms.append(
            f'{indent}(wire (pts (xy {self._fmt_number(start[0])} '
            f'{self._fmt_number(start[1])}) (xy {self._fmt_number(end[0])} '
            f'{self._fmt_number(end[1])})) (stroke (width 0) (type default)) '
            f'(uuid "{uuid.uuid4()}"))\n'
        )
        self._pending_wire_ends.update((start, end))

    def add_label(self, label: LabelSpec) -> None:
        """Queue a label using the KiCad schematic S-expression format.

        Format: https://dev-docs.kicad.org/en/file-formats/sexpr-schematic/
        """
        font = (
            f"(size {self._fmt_number(label.font_size)} "
            f"{self._fmt_number(label.font_size)})"
        )
        if label.font_thickness is not None:
            font += f" (thickness {self._fmt_number(label.font_thickness)})"
        if label.font_face:
            font += f" (face {self._quote_string(label.font_face)})"
        if label.bold:
            font += " bold"
        if label.italic:
            font += " italic"
        self._pending_forms.append(
            f'{self._indent()}(label {self._quote_string(label.name)} '
            f'(at {self._fmt_number(label.position[0])} '
            f'{self._fmt_number(label.position[1])} {label.angle}) '
            f'(effects (font {font}) (justify {label.justification})) '
            f'(uuid "{uuid.uuid4()}"))\n'
        )
        self._pending_labels.append(
            (label.name, label.position[0], label.position[1])
        )

    def add_no_connect(self, position: Point) -> None:
        """Queue a marker using KiCad's documented no_connect form.

        Format: https://dev-docs.kicad.org/en/file-formats/sexpr-schematic/
        """
        self._pending_forms.append(
            f'{self._indent()}(no_connect (at {self._fmt_number(position[0])} '
            f'{self._fmt_number(position[1])}) (uuid "{uuid.uuid4()}"))\n'
        )

    def serialize(self) -> str:
        if not self._pending_forms:
            return self.text
        block = "".join(self._pending_forms)
        insertion_point = self._top_level_marker_position(
            self.text,
            ("(sheet_instances", "(symbol_instances", "(embedded_fonts"),
        )
        if insertion_point is not None:
            return self.text[:insertion_point] + block + self.text[insertion_point:]
        insertion_point = self.text.rfind(")")
        if insertion_point < 0:
            raise ValueError("Schematic has no closing parenthesis for insertion")
        return (
            self.text[:insertion_point]
            + "\n"
            + block
            + self.text[insertion_point:]
        )

    def _indent(self) -> str:
        return "\t" if "\t" in self.text else "  "

    @staticmethod
    def _fmt_number(value: float) -> str:
        numeric = float(value)
        if abs(numeric - round(numeric)) < 1e-9:
            return str(int(round(numeric)))
        return format(numeric, ".4f").rstrip("0").rstrip(".")

    @staticmethod
    def _quote_string(value: str) -> str:
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'

    @staticmethod
    def _children(form: list[Any], tag: str) -> Iterable[list[Any]]:
        return (
            item for item in form
            if isinstance(item, list) and item and item[0] == tag
        )

    @staticmethod
    def _top_level_marker_position(
        text: str,
        markers: tuple[str, ...],
    ) -> int | None:
        depth = 0
        in_string = False
        escaped = False
        in_comment = False
        positions: list[int] = []
        index = 0

        while index < len(text):
            char = text[index]
            if in_comment:
                if char == "\n":
                    in_comment = False
                index += 1
                continue
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                index += 1
                continue
            if char == ";":
                in_comment = True
            elif char == '"':
                in_string = True
            elif char == "(":
                if depth == 1:
                    for marker in markers:
                        if text.startswith(marker, index):
                            positions.append(text.rfind("\n", 0, index) + 1)
                depth += 1
            elif char == ")":
                depth -= 1
            index += 1

        return min(positions) if positions else None

    def _symbol_reference(self, symbol_form: Sequence[Any]) -> Optional[str]:
        property_reference: Optional[str] = None
        for entry in symbol_form:
            if not isinstance(entry, list) or not entry:
                continue
            if entry[0] == "property" and len(entry) >= 3 and entry[1] == "Reference":
                property_reference = str(entry[2])
            if entry[0] == "instances":
                for instance in entry:
                    if isinstance(instance, list) and instance and instance[0] == "project":
                        for node in instance:
                            if isinstance(node, list) and node and node[0] == "path":
                                for child in node:
                                    if isinstance(child, list) and child and child[0] == "reference":
                                        return str(child[1])
        return property_reference

    def _symbol_lib_id(self, symbol_form: Sequence[Any]) -> str:
        for entry in symbol_form:
            if isinstance(entry, list) and entry and entry[0] == "lib_id" and len(entry) >= 2:
                return str(entry[1])
        return ""

    def _symbol_at(self, symbol_form: Sequence[Any]) -> tuple[float, float, float]:
        for entry in symbol_form:
            if isinstance(entry, list) and entry and entry[0] == "at" and len(entry) >= 4:
                return float(entry[1]), float(entry[2]), float(entry[3])
        return 0.0, 0.0, 0.0

    def _symbol_unit(self, symbol_form: Sequence[Any]) -> int:
        for entry in symbol_form:
            if isinstance(entry, list) and entry and entry[0] == "unit" and len(entry) >= 2:
                return int(entry[1])
        return 1

    def _symbol_body_style(self, symbol_form: Sequence[Any]) -> int:
        for entry in symbol_form:
            if isinstance(entry, list) and entry and entry[0] == "body_style" and len(entry) >= 2:
                return int(entry[1])
        return 1

    def _symbol_pins(self, symbol_form: Sequence[Any]) -> list[PinRecord]:
        pins: list[PinRecord] = []
        for entry in symbol_form:
            if not isinstance(entry, list) or not entry or entry[0] != "pin":
                continue
            pin_number = ""
            pin_name = ""
            pin_x = 0.0
            pin_y = 0.0
            electrical = "unspecified"
            for node in entry:
                if not isinstance(node, list) or not node:
                    continue
                if node[0] == "at" and len(node) >= 3:
                    pin_x = float(node[1])
                    pin_y = float(node[2])
                elif node[0] == "name" and len(node) >= 2:
                    pin_name = str(node[1])
                elif node[0] == "number" and len(node) >= 2:
                    pin_number = str(node[1])
                elif node[0] == "electrical" and len(node) >= 2:
                    electrical = str(node[1])
            if pin_number:
                pins.append(PinRecord(number=pin_number, name=pin_name, x=pin_x, y=pin_y, electrical=electrical))
        return pins

    def _library_pins_for_instance(self, lib_id: str, unit: int, body_style: int) -> list[dict[str, Any]]:
        if not lib_id:
            return []
        for lib_symbol in self.lib_symbols:
            if not isinstance(lib_symbol, list) or not lib_symbol or lib_symbol[0] != "symbol":
                continue
            if len(lib_symbol) < 2 or not isinstance(lib_symbol[1], str):
                continue
            if lib_symbol[1] != lib_id:
                continue
            pins: list[dict[str, Any]] = []
            for unit_symbol in lib_symbol[2:]:
                if not isinstance(unit_symbol, list) or len(unit_symbol) < 2 or unit_symbol[0] != "symbol":
                    continue
                name = str(unit_symbol[1])
                suffix = name.rsplit("_", 2)
                if len(suffix) != 3:
                    continue
                try:
                    pin_unit, pin_style = int(suffix[-2]), int(suffix[-1])
                except ValueError:
                    continue
                if pin_unit not in (0, unit) or pin_style != body_style:
                    continue
                for pin_entry in unit_symbol[2:]:
                    parsed = self._parse_pin_entry(pin_entry)
                    if parsed is not None:
                        pins.append(parsed)
            return pins
        return []

    def _parse_pin_entry(self, pin_entry: Any) -> Optional[dict[str, Any]]:
        if not isinstance(pin_entry, list) or not pin_entry or pin_entry[0] != "pin":
            return None
        pin_number = ""
        pin_name = ""
        point = (0.0, 0.0)
        electrical = str(pin_entry[1]) if len(pin_entry) > 1 else "unspecified"
        for node in pin_entry:
            if not isinstance(node, list) or not node:
                continue
            if node[0] == "number" and len(node) >= 2:
                pin_number = str(node[1])
            elif node[0] == "name" and len(node) >= 2:
                pin_name = str(node[1])
            elif node[0] == "at" and len(node) >= 4:
                point = (float(node[1]), float(node[2]))
        if not pin_number:
            return None
        return {
            "number": pin_number,
            "name": pin_name,
            "electrical": electrical,
            "x": point[0],
            "y": point[1],
        }
