import hashlib
import json
import zipfile

import pytest

from tools import build_pcm_package


def test_build_package_has_only_pcm_archive_content_and_submission_metadata(
    tmp_path, monkeypatch
):
    schemas = {
        build_pcm_package.PCM_SCHEMA_URL: {
            "type": "object",
            "required": [
                "name",
                "description",
                "description_full",
                "identifier",
                "type",
                "author",
                "license",
                "resources",
                "versions",
            ],
            "properties": {
                "versions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["version", "status", "kicad_version"],
                    },
                }
            },
        },
        build_pcm_package.PLUGIN_SCHEMA_URL: {
            "type": "object",
            "required": ["identifier", "name", "description", "runtime", "actions"],
            "properties": {
                "actions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["identifier", "name", "description", "entrypoint"],
                    },
                }
            },
        },
    }
    monkeypatch.setattr(
        build_pcm_package, "_load_schema", lambda url: schemas[url]
    )
    output_dir = tmp_path / "dist"

    archive_path, submission_path = build_pcm_package.build_package(
        build_pcm_package.PROJECT_ROOT,
        output_dir,
        "1.2.3",
    )

    with zipfile.ZipFile(archive_path) as archive:
        names = set(archive.namelist())
        assert "metadata.json" in names
        assert "plugins/plugin.json" in names
        assert "plugins/main.py" in names
        assert "plugins/requirements.txt" in names
        assert "plugins/Cubemx2sch_Light.png" in names
        assert "plugins/Cubemx2sch_Dark.png" in names
        assert "resources/icon.png" in names
        assert "plugins/cubemx_kicad_netlabels/gui.py" in names
        assert all(
            name in {"metadata.json", "resources/icon.png"}
            or name.startswith("plugins/")
            for name in names
        )
        assert archive.getinfo("resources/icon.png").file_size > 0
        archive_metadata = json.loads(archive.read("metadata.json"))

    submission_metadata = json.loads(submission_path.read_text(encoding="utf-8"))
    archive_version = archive_metadata["versions"][0]
    submission_version = submission_metadata["versions"][0]
    assert "download_url" not in archive_version
    assert "download_sha256" not in archive_version
    assert submission_version["download_sha256"] == hashlib.sha256(
        archive_path.read_bytes()
    ).hexdigest()
    assert submission_version["download_size"] == archive_path.stat().st_size
    with zipfile.ZipFile(archive_path) as archive:
        assert submission_version["install_size"] == sum(
            info.file_size for info in archive.infolist()
        )
    assert archive_metadata["identifier"] == build_pcm_package.PACKAGE_IDENTIFIER
    assert submission_version["runtime"] == "ipc"
    manifest = json.loads(
        (build_pcm_package.PROJECT_ROOT / "kicad_plugin" / "plugin.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest["actions"][0]["show-button"] is True
    assert manifest["actions"][0]["icons-light"] == ["Cubemx2sch_Light.png"]
    assert manifest["actions"][0]["icons-dark"] == ["Cubemx2sch_Dark.png"]


def test_build_package_rejects_invalid_version(tmp_path):
    with pytest.raises(ValueError, match="Invalid PCM package version"):
        build_pcm_package.build_package(
            build_pcm_package.PROJECT_ROOT,
            tmp_path,
            "../1.2.3",
        )
