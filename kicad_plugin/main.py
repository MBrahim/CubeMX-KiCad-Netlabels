from __future__ import annotations

import sys
from pathlib import Path


def _show_error(message: str) -> None:
    try:
        import tkinter
        from tkinter import messagebox
    except ImportError:
        print(message, file=sys.stderr)
        return

    try:
        root = tkinter.Tk()
        root.withdraw()
        messagebox.showerror("CubeMX KiCad Netlabels", message)
        root.destroy()
    except tkinter.TclError:
        print(message, file=sys.stderr)


def main() -> int:
    plugin_dir = Path(__file__).resolve().parent
    sys.path.insert(0, str(plugin_dir))

    try:
        import PySide6  # noqa: F401
    except ImportError:
        _show_error(
            "PySide6 is required to open CubeMX KiCad Netlabels.\n\n"
            f'Install it in this KiCad plugin environment with:\n'
            f'"{sys.executable}" -m pip install PySide6\n'
            "Then restart the PCB Editor and try again."
        )
        return 1

    try:
        from kipy import KiCad
        from kipy.client import ApiError
        from kipy.proto.common.types import DocumentType
    except ImportError:
        _show_error(
            "kicad-python is required to detect the current project's folder.\n\n"
            f'Install it in this KiCad plugin environment with:\n'
            f'"{sys.executable}" -m pip install "kicad-python>=0.2.0"\n'
            "Then restart the PCB Editor and try again."
        )
        return 1

    kicad = KiCad()
    boards = kicad.get_open_documents(DocumentType.DOCTYPE_PCB)
    if len(boards) != 1:
        _show_error(
            "Cannot determine the current project folder unambiguously. "
            "Keep exactly one PCB document open, then try again."
        )
        return 1

    try:
        board = kicad.get_board()
    except ApiError as exc:
        _show_error(
            f"Could not read the open PCB project's folder from KiCad:\n{exc}"
        )
        return 1

    project_directory = board.document.project.path
    if not project_directory or not Path(project_directory).is_dir():
        _show_error(
            "KiCad did not provide an existing project folder. "
            "The schematic picker cannot start in the project folder."
        )
        return 1

    from cubemx_kicad_netlabels.gui import launch

    launch(project_directory=project_directory)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
