import sys
from types import ModuleType, SimpleNamespace

import pytest

pytest.importorskip("PySide6")

import kicad_plugin.main as plugin_main
import cubemx_kicad_netlabels.gui as gui


def test_plugin_passes_open_board_project_directory_to_gui(monkeypatch, tmp_path):
    project_directory = str(tmp_path)

    class FakeKiCad:
        def get_open_documents(self, document_type):
            assert document_type == "pcb"
            return [object()]

        def get_board(self):
            return SimpleNamespace(
                document=SimpleNamespace(
                    project=SimpleNamespace(path=project_directory)
                )
            )

    kipy = ModuleType("kipy")
    kipy.__path__ = []
    kipy.KiCad = FakeKiCad
    client = ModuleType("kipy.client")
    client.ApiError = type("ApiError", (Exception,), {})
    proto = ModuleType("kipy.proto")
    proto.__path__ = []
    common = ModuleType("kipy.proto.common")
    common.__path__ = []
    common_types = ModuleType("kipy.proto.common.types")
    common_types.DocumentType = SimpleNamespace(DOCTYPE_PCB="pcb")
    monkeypatch.setitem(sys.modules, "kipy", kipy)
    monkeypatch.setitem(sys.modules, "kipy.client", client)
    monkeypatch.setitem(sys.modules, "kipy.proto", proto)
    monkeypatch.setitem(sys.modules, "kipy.proto.common", common)
    monkeypatch.setitem(sys.modules, "kipy.proto.common.types", common_types)

    calls = []
    monkeypatch.setattr(
        gui, "launch", lambda **kwargs: calls.append(kwargs)
    )

    assert plugin_main.main() == 0
    assert calls == [{"project_directory": project_directory}]
