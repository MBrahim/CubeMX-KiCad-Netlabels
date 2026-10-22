from __future__ import annotations

import csv
from pathlib import Path

GENERIC = (
    "GPIO_Input",
    "GPIO_Output",
    "GPIO_Analog",
    "n/a",
    "na",
    "-",
)


def clean_net(value: object) -> str:
    text = str(value or "").strip()
    text = " ".join(text.split())
    text = text.replace(" ", "_")
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-+/\\[]")
    cleaned = "".join(ch if ch in allowed else "_" for ch in text)
    return cleaned


def _is_generic(value: str) -> bool:
    lowered = value.lower()
    return lowered in {item.lower() for item in GENERIC} or lowered.startswith("gpio_")


def _detect_delimiter(sample: str) -> str:
    for candidate in (";", ",", "\t"):
        if sample.count(candidate) > 0:
            return candidate
    return ","


def read_cube_csv(path, column: str = "Label", fallback_signal: bool = False, fallback_name: bool = False) -> dict[str, str]:
    file_path = Path(path)
    with file_path.open("r", encoding="utf-8-sig", newline="") as handle:
        sample = handle.read(4096)
        handle.seek(0)
        delimiter = _detect_delimiter(sample)
        reader = csv.DictReader(handle, delimiter=delimiter)
        if reader.fieldnames is None:
            raise SystemExit(f"CSV file {file_path} is empty or missing a header")

        normalized = {name.strip().lower(): name for name in reader.fieldnames if name is not None}
        if "position" not in normalized:
            raise SystemExit(f"CSV file {file_path} is missing the required 'Position' column")

        chosen_column = column.strip().lower()
        if chosen_column not in {"label", "signal", "name"}:
            raise SystemExit("--column must be one of Label, Signal or Name")

        candidate_keys = []
        if chosen_column == "label":
            candidate_keys.append("label")
        elif chosen_column == "signal":
            candidate_keys.append("signal")
        else:
            candidate_keys.append("name")
        if fallback_signal:
            candidate_keys.append("signal")
        if fallback_name:
            candidate_keys.append("name")
        candidate_keys = list(dict.fromkeys(candidate_keys))

        values: dict[str, str] = {}
        seen: set[str] = set()
        net_to_pins: dict[str, set[str]] = {}

        for row in reader:
            if row is None:
                continue
            position = (row.get(normalized.get("position", "Position"), "") or "").strip()
            if not position:
                continue
            if position in seen:
                print(f"Warning: pin {position} appears twice in {file_path}; keeping the first entry.")
                continue
            seen.add(position)

            chosen = ""
            for key in candidate_keys:
                raw_value = row.get(normalized.get(key, key), "")
                if raw_value is None:
                    continue
                net_name = clean_net(raw_value)
                if net_name and not _is_generic(net_name):
                    chosen = net_name
                    break
            if not chosen:
                continue

            values[position] = chosen
            net_to_pins.setdefault(chosen, set()).add(position)

        for net_name, pins in sorted(net_to_pins.items()):
            if len(pins) > 1:
                print(f"Warning: net '{net_name}' is assigned to multiple pins ({', '.join(sorted(pins))}); this looks like a shorted net.")

        if not values:
            raise SystemExit(f"CSV file {file_path} does not contain any usable net names")
        return values
