import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from cubemx_kicad_netlabels.gui import NetLabelGui, build_cli_arguments


def test_gui_builds_arguments_using_mils_and_cli_supported_options():
    assert build_cli_arguments(
        csv_path="pins.csv",
        schematic_path="board.kicad_sch",
        output_path="board_labeled.kicad_sch",
        reference="U1",
        column="Signal",
        net_length_mils="auto",
        grid_mils=50,
        font_size_mils=50,
        minimum_stub_mils=100,
        font_face="KiCad Font",
        auto_thickness=True,
        bold=True,
        fallback_signal=True,
    ) == [
        "pins.csv",
        "board.kicad_sch",
        "board_labeled.kicad_sch",
        "--reference",
        "U1",
        "--column",
        "Signal",
        "--stub",
        "100",
        "--net-length",
        "auto",
        "--grid",
        "50",
        "--font-size",
        "50",
        "--font-face",
        "KiCad Font",
        "--auto-thickness",
        "--bold",
        "--fallback-signal",
    ]


def test_gui_builds_auto_stub_and_default_font_arguments():
    arguments = build_cli_arguments(
        csv_path="pins.csv",
        schematic_path="board.kicad_sch",
        output_path="board_labeled.kicad_sch",
        reference="U1",
        column="Label",
        net_length_mils="auto",
        grid_mils=50,
        font_size_mils=50,
        minimum_stub_mils=300,
        auto_thickness=True,
    )

    assert arguments[arguments.index("--net-length") + 1] == "auto"
    assert "--font-face" not in arguments


def test_gui_uses_explicit_thickness_when_auto_thickness_is_disabled():
    arguments = build_cli_arguments(
        csv_path="pins.csv",
        schematic_path="board.kicad_sch",
        output_path="",
        reference="U1",
        column="Label",
        net_length_mils=300,
        grid_mils=50,
        font_size_mils=50,
        minimum_stub_mils=300,
        font_thickness_mils=6,
        auto_thickness=False,
        italic=True,
        in_place=True,
        force=True,
    )

    assert "--auto-thickness" not in arguments
    assert arguments[-5:] == [
        "--font-thickness",
        "6",
        "--italic",
        "--in-place",
        "--force",
    ]


def test_font_thickness_control_does_not_overlap_auto_thickness_checkbox():
    app = QApplication.instance() or QApplication([])
    window = NetLabelGui()
    window.show()
    app.processEvents()

    assert not window.font_thickness.geometry().intersects(
        window.auto_thickness.geometry()
    )
    assert window.font_thickness.isEnabled() == (
        not window.auto_thickness.isChecked()
    )
    window.auto_thickness.setChecked(not window.auto_thickness.isChecked())
    assert window.font_thickness.isEnabled() == (
        not window.auto_thickness.isChecked()
    )
    window.close()


def test_net_length_custom_mode_shows_custom_length_input():
    app = QApplication.instance() or QApplication([])
    window = NetLabelGui()
    window.show()
    app.processEvents()

    window.length_mode.setCurrentText("Auto fit")
    app.processEvents()
    assert not window.net_length.isVisible()
    window.length_mode.setCurrentText("Custom")
    app.processEvents()
    assert window.net_length.isVisible()
    window.close()


def test_gui_font_list_starts_with_kicad_default_choices():
    app = QApplication.instance() or QApplication([])
    window = NetLabelGui()

    assert [window.font_name.itemText(index) for index in range(2)] == [
        "Default Font",
        "KiCad Font",
    ]
    window.close()


def test_schematic_picker_starts_in_project_directory(monkeypatch, tmp_path):
    app = QApplication.instance() or QApplication([])
    project_directory = str(tmp_path)
    window = NetLabelGui(project_directory=project_directory)
    calls = []
    monkeypatch.setattr(
        "cubemx_kicad_netlabels.gui.QFileDialog.getOpenFileName",
        lambda *args: (calls.append(args) or ("", "")),
    )

    window._browse_input()

    assert calls[0][2] == project_directory
    window.close()


def test_csv_picker_starts_in_project_directory(monkeypatch, tmp_path):
    app = QApplication.instance() or QApplication([])
    project_directory = str(tmp_path)
    window = NetLabelGui(project_directory=project_directory)
    calls = []
    monkeypatch.setattr(
        "cubemx_kicad_netlabels.gui.QFileDialog.getOpenFileName",
        lambda *args: (calls.append(args) or ("", "")),
    )

    window._browse_csv()

    assert calls[0][2] == project_directory
    window.close()


def test_schematic_picker_keeps_default_directory_without_project():
    app = QApplication.instance() or QApplication([])
    window = NetLabelGui()
    assert window._project_directory == ""
    window.close()
