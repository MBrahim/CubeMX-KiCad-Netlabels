from __future__ import annotations

import re
from typing import Any


class SexprParseError(ValueError):
    pass


def parse_sexpr(text: str, index: int = 0):
    text = text or ""
    index = _skip_ws_and_comments(text, index)
    if index >= len(text):
        raise SexprParseError("Unexpected end of input")

    ch = text[index]
    if ch == "(":
        values: list[Any] = []
        index += 1
        while True:
            index = _skip_ws_and_comments(text, index)
            if index >= len(text):
                raise SexprParseError("Unterminated list")
            if text[index] == ")":
                return values, index + 1
            item, index = parse_sexpr(text, index)
            values.append(item)

    if ch == '"':
        return _read_string(text, index)
    if ch == ")":
        raise SexprParseError(f"Unexpected ')' at {index}")

    atom_start = index
    while index < len(text) and not text[index].isspace() and text[index] not in '()"':
        index += 1
    atom = text[atom_start:index]
    if not atom:
        raise SexprParseError(f"Invalid atom at {index}")
    return _coerce_atom(atom), index


def _coerce_atom(atom: str):
    if atom.lower() in {"true", "yes"}:
        return True
    if atom.lower() in {"false", "no"}:
        return False
    if re.fullmatch(r"[-+]?\d+", atom):
        return int(atom)
    if re.fullmatch(r"[-+]?\d+\.\d+([eE][-+]?\d+)?", atom):
        return float(atom)
    return atom


def _read_string(text: str, index: int):
    index += 1
    chars: list[str] = []
    while index < len(text):
        ch = text[index]
        if ch == "\\":
            index += 1
            if index >= len(text):
                raise SexprParseError("Trailing escape in string")
            escaped = text[index]
            chars.append({"n": "\n", "r": "\r", "t": "\t", '"': '"', "\\": "\\"}.get(escaped, escaped))
            index += 1
            continue
        if ch == '"':
            return "".join(chars), index + 1
        chars.append(ch)
        index += 1
    raise SexprParseError("Unterminated string")


def _skip_ws_and_comments(text: str, index: int) -> int:
    while index < len(text):
        if text[index].isspace():
            index += 1
            continue
        if text[index] == ";":
            newline = text.find("\n", index)
            if newline == -1:
                return len(text)
            index = newline + 1
            continue
        break
    return index


def read_sexpr_forms(text: str):
    forms = []
    index = 0
    while index < len(text):
        index = _skip_ws_and_comments(text, index)
        if index >= len(text):
            break
        start = index
        value, next_index = parse_sexpr(text, index)
        forms.append((start, value, next_index))
        index = next_index
    return forms
