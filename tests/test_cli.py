from cubemx_kicad_netlabels.cli import main


def test_list_references_accepts_schematic_without_a_csv(capsys):
    exit_code = main(["--list-references", "tests/fixtures/STM32F1.kicad_sch"])

    assert exit_code == 0
    assert capsys.readouterr().out.splitlines() == ["U1"]


def test_inspect_accepts_schematic_without_a_csv_and_reports_mils(capsys):
    exit_code = main([
        "--inspect",
        "tests/fixtures/STM32F1.kicad_sch",
        "--reference",
        "U1",
    ])

    assert exit_code == 0
    assert "14: PA4 @ (6250.00, 3100.00) mils" in capsys.readouterr().out.splitlines()
