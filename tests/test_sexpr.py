from cubemx_kicad_netlabels import (
    FileBackend,
    LabelSpec,
    SchematicBackend,
    parse_sexpr,
    read_sexpr_forms,
)


def test_parse_sexpr_handles_nested_lists_and_strings():
    text = '(kicad_sch (version 20240609) (label "LED 1" (at 1 2 0)))'
    value, _ = parse_sexpr(text, 0)
    assert value[0] == "kicad_sch"
    assert value[2][0] == "label"
    assert value[2][1] == "LED 1"


def test_top_level_forms_return_offsets():
    text = '(one 1) (two (three 3))'
    forms = read_sexpr_forms(text)
    assert len(forms) == 2
    assert forms[0][0] == 0
    assert forms[1][2] == text.rfind(")") + 1


def test_file_backend_reads_reference_from_instances():
    backend = FileBackend("tests/fixtures/simple.kicad_sch")
    refs = backend.list_references()
    assert refs == ["U1"]
    pins = backend.pins_for_reference("U1")
    assert [pin.number for pin in pins] == ["1", "2"]


def test_instance_reference_takes_precedence_over_property(tmp_path):
    source = open("tests/fixtures/simple.kicad_sch", encoding="utf-8").read()
    path = tmp_path / "stale_property.kicad_sch"
    path.write_text(source.replace('(property "Reference" "U1")', '(property "Reference" "U?")'), encoding="utf-8")

    assert FileBackend(path).list_references() == ["U1"]


def test_file_backend_implements_read_and_edit_backend_contract():
    backend = FileBackend("tests/fixtures/simple.kicad_sch")
    source = backend.text
    assert isinstance(backend, SchematicBackend)

    backend.add_wire((1.0, 2.0), (3.0, 2.0))
    backend.add_label(
        LabelSpec(
            name="TEST_NET",
            position=(3.0, 2.0),
            angle=0,
            justification="right bottom",
            font_size=1.27,
        )
    )
    backend.add_no_connect((4.0, 5.0))
    updated = backend.serialize()

    assert '(wire (pts (xy 1 2) (xy 3 2))' in updated
    assert '(label "TEST_NET" (at 3 2 0)' in updated
    assert '(no_connect (at 4 5)' in updated
    assert backend.text == source
    assert updated.startswith(source[:100])
    assert len(read_sexpr_forms(updated)) == 1
