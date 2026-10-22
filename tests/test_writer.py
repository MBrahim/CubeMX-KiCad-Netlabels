import shutil

import pytest

from cubemx_kicad_netlabels.cli import main
from cubemx_kicad_netlabels.schematic import FileBackend
from cubemx_kicad_netlabels.writer import insert_net_labels


def test_insert_net_labels_writes_wire_and_label_blocks():
    backend = FileBackend("tests/fixtures/STM32F1.kicad_sch")
    src = backend.text
    updated = insert_net_labels(src, "U1", {"14": "BTN_1", "15": "LED_RED"}, backend)
    assert '(wire (pts (xy 158.75 78.74) (xy 167.64 78.74))' in updated
    assert '(label "BTN_1"' in updated
    assert '(label "LED_RED"' in updated
    assert '(at 167.64 78.74 0) (effects (font (size 1.27 1.27)) (justify right bottom))' in updated


def test_left_facing_label_uses_justification_toward_symbol_interior():
    backend = FileBackend("tests/fixtures/STM32F1.kicad_sch")
    updated = insert_net_labels(
        backend.text,
        "U1",
        {"21": "LEFT_NET"},
        backend,
    )

    assert '(label "LEFT_NET" (at 110.49 121.92 180) ' \
           '(effects (font (size 1.27 1.27)) (justify left bottom))' in updated


def test_stm32_fixture_pin_positions_are_in_sheet_coordinates():
    backend = FileBackend("tests/fixtures/STM32F1.kicad_sch")
    pins = {pin["number"]: pin for pin in backend.resolve_reference_pins("U1")}

    assert (pins["14"]["x"], pins["14"]["y"]) == (158.75, 78.74)
    assert (pins["15"]["x"], pins["15"]["y"]) == (158.75, 81.28)
    assert (round(pins["21"]["x"], 2), round(pins["21"]["y"], 2)) == (123.19, 121.92)


def test_writer_is_idempotent_for_existing_generated_wire(tmp_path):
    backend = FileBackend("tests/fixtures/STM32F1.kicad_sch")
    updated = insert_net_labels(
        backend.text,
        "U1",
        {"14": "BTN_1", "15": "LED_RED"},
        backend,
    )
    output = tmp_path / "labeled.kicad_sch"
    output.write_bytes(updated.encode("utf-8"))

    reread = FileBackend(output)
    assert insert_net_labels(
        reread.text,
        "U1",
        {"14": "BTN_1", "15": "LED_RED"},
        reread,
    ) == updated


def test_cli_inserts_labels_for_matching_reference(tmp_path):
    out = tmp_path / "stm32_out.kicad_sch"
    exit_code = main([
        "examples/pinout_example.csv",
        "tests/fixtures/STM32F1.kicad_sch",
        str(out),
        "--reference",
        "U1",
    ])
    assert exit_code == 0
    text = out.read_text(encoding="utf-8")
    assert '(label "BTN_1"' in text
    assert '(label "LED_RED"' in text
    assert '(at 167.64 78.74 0)' in text
    btn_label = text.split('(label "BTN_1"', 1)[1].split('(uuid', 1)[0]
    assert "(size 1.27 1.27)" in btn_label
    assert "(thickness " not in btn_label


def test_cli_dimensions_are_in_mils_and_convert_to_kicad_mm(tmp_path):
    out = tmp_path / "mils_out.kicad_sch"
    exit_code = main([
        "examples/pinout_example.csv",
        "tests/fixtures/STM32F1.kicad_sch",
        str(out),
        "--reference",
        "U1",
        "--stub",
        "200",
        "--grid",
        "100",
        "--font-size",
        "60",
        "--font-thickness",
        "5",
    ])
    assert exit_code == 0
    text = out.read_text(encoding="utf-8")
    assert "(xy 158.75 78.74) (xy 172.72 78.74)" in text
    assert "(size 1.524 1.524) (thickness 0.127)" in text


def test_cli_auto_stub_grows_with_label_length_and_snaps_to_grid(tmp_path):
    out = tmp_path / "auto_stub.kicad_sch"
    exit_code = main([
        "examples/pinout_example.csv",
        "tests/fixtures/STM32F1.kicad_sch",
        str(out),
        "--reference",
        "U1",
        "--stub",
        "100",
        "--grid",
        "50",
        "--font-size",
        "100",
    ])

    assert exit_code == 0
    text = out.read_text(encoding="utf-8")
    assert '(label "DEBUG_TX"' in text
    assert "(xy 158.75 83.82) (xy 179.07 83.82)" in text


def test_auto_fit_reserves_space_between_inward_label_and_pin_numbers(tmp_path):
    out = tmp_path / "label_clearance.kicad_sch"
    exit_code = main([
        "examples/pinout_example.csv",
        "tests/fixtures/STM32F1.kicad_sch",
        str(out),
        "--reference",
        "U1",
        "--column",
        "Name",
        "--net-length",
        "auto",
        "--font-size",
        "50",
        "--grid",
        "100",
    ])

    assert exit_code == 0
    text = out.read_text(encoding="utf-8")
    assert '(label "PA0" (at 167.64 78.74 0)' in text
    assert '(justify right bottom)' in text


def test_long_auto_fit_label_gets_text_and_pin_number_clearance():
    backend = FileBackend("tests/fixtures/STM32F1.kicad_sch")
    updated = insert_net_labels(
        backend.text,
        "U1",
        {"14": "RCC_OSC_IN"},
        backend,
        stub=300 * 0.0254,
        grid=100 * 0.0254,
        font_size=50 * 0.0254,
    )

    assert "(xy 158.75 78.74) (xy 172.72 78.74)" in updated
    assert '(label "RCC_OSC_IN" (at 172.72 78.74 0)' in updated
    assert '(justify right bottom)' in updated


def test_cli_custom_net_length_overrides_auto_fit(tmp_path):
    out = tmp_path / "custom_net_length.kicad_sch"
    exit_code = main([
        "examples/pinout_example.csv",
        "tests/fixtures/STM32F1.kicad_sch",
        str(out),
        "--reference",
        "U1",
        "--stub",
        "300",
        "--net-length",
        "200",
        "--grid",
        "50",
    ])

    assert exit_code == 0
    text = out.read_text(encoding="utf-8")
    assert "(xy 158.75 78.74) (xy 163.83 78.74)" in text


def test_in_place_writes_backup_and_corrected_labels(tmp_path):
    schematic = tmp_path / "STM32F1.kicad_sch"
    shutil.copyfile("tests/fixtures/STM32F1.kicad_sch", schematic)
    original = schematic.read_bytes()

    exit_code = main([
        "examples/pinout_example.csv",
        str(schematic),
        "--reference",
        "U1",
        "--in-place",
        "--force",
    ])

    assert exit_code == 0
    backups = list(tmp_path.glob("STM32F1.kicad_sch.*.bak"))
    assert len(backups) == 1
    assert backups[0].read_bytes() == original
    assert '(wire (pts (xy 158.75 78.74) (xy 167.64 78.74))' in schematic.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "changed_at, insertion",
    [
        ("(at 140.97 101.6 0)", "(at 140.97 101.6 90)"),
        ("(at 140.97 101.6 0)", "(at 140.97 101.6 0)\n\t\t(mirror x)"),
    ],
)
def test_unverified_symbol_transforms_fail_safely(tmp_path, changed_at, insertion):
    source = open("tests/fixtures/STM32F1.kicad_sch", encoding="utf-8").read()
    transformed = source.replace(changed_at, insertion, 1)
    path = tmp_path / "transformed.kicad_sch"
    path.write_text(transformed, encoding="utf-8")

    backend = FileBackend(path)
    with pytest.raises(ValueError, match="not yet verified"):
        backend.resolve_reference_pins("U1")
