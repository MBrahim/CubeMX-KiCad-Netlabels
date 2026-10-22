from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TypedDict


Point = tuple[float, float]


@dataclass(frozen=True)
class PinRecord:
    number: str
    name: str
    x: float
    y: float
    electrical: str = "unspecified"


class PinPlacement(TypedDict):
    number: str
    name: str
    electrical: str
    x: float
    y: float


@dataclass(frozen=True)
class LabelSpec:
    name: str
    position: Point
    angle: int
    justification: str
    font_size: float
    font_face: str | None = None
    font_thickness: float | None = None
    bold: bool = False
    italic: bool = False


class SchematicBackend(ABC):
    """Interface for reading and editing schematic objects."""

    @abstractmethod
    def list_references(self) -> list[str]:
        """Return placed symbol references."""

    @abstractmethod
    def pins_for_reference(self, reference: str) -> list[PinRecord]:
        """Return the symbol pins associated with a placed reference."""

    @abstractmethod
    def resolve_reference_pins(self, reference: str) -> list[PinPlacement]:
        """Return pin numbers and coordinates in sheet space."""

    @abstractmethod
    def existing_wire_ends(self) -> set[Point]:
        """Return existing and newly queued wire endpoints."""

    @abstractmethod
    def existing_labels(self) -> list[tuple[str, float, float]]:
        """Return existing and newly queued label anchors."""

    @abstractmethod
    def add_wire(self, start: Point, end: Point) -> None:
        """Queue a wire between two sheet-coordinate points."""

    @abstractmethod
    def add_label(self, label: LabelSpec) -> None:
        """Queue a net label."""

    @abstractmethod
    def add_no_connect(self, position: Point) -> None:
        """Queue a no-connect marker at a pin."""

    @abstractmethod
    def serialize(self) -> str:
        """Return the schematic with queued edits applied."""
