from __future__ import annotations

import argparse
import hashlib
from importlib.resources import path
import json
import re
import struct
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

from jsonschema import validate


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_IDENTIFIER = "com.github.mbrahim.cubemx-kicad-netlabels"
PACKAGE_NAME = "CubeMX KiCad Netlabels"
PACKAGE_DESCRIPTION = "Create KiCad schematic net labels from a CubeMX pinout CSV."
PACKAGE_DESCRIPTION_FULL = (
    "A KiCad PCB-editor action that opens a graphical tool for creating schematic "
    "net labels from STM32CubeMX CSV pinout files. Choose the CSV and schematic "
    "in the GUI, configure label placement, and generate a KiCad schematic output."
)
PCM_SCHEMA_URL = "https://go.kicad.org/pcm/schemas/v2"
PLUGIN_SCHEMA_URL = "https://go.kicad.org/api/schemas/v1"
GITHUB_RELEASE_URL = (
    "https://github.com/MBrahim/CubeMX-KiCad-Netlabels/releases/download/"
    "v{version}/cubemx-kicad-netlabels-{version}.zip"
)
PLUGIN_FILES = (
    Path("plugin.json"),
    Path("main.py"),
    Path("requirements.txt"),
    Path("Cubemx2sch_Dark.png"),
    Path("Cubemx2sch_Light.png"),
)
PACKAGE_MODULE = Path("cubemx_kicad_netlabels")
PCM_ICON = Path("resources") / "icon.png"


def _project_version(project_root: Path) -> str:
    pyproject = (project_root / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'(?m)^version\s*=\s*"([^"]+)"\s*$', pyproject)
    if match is None:
        raise ValueError("Could not find the project version in pyproject.toml")
    return match.group(1)


def _load_schema(url: str) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "CubeMX-KiCad-Netlabels PCM package builder"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        schema = json.load(response)
    if not isinstance(schema, dict):
        raise ValueError(f"Schema at {url} is not a JSON object")
    return schema


def _metadata(version: str) -> dict[str, Any]:
    """Create metadata per https://go.kicad.org/pcm/schemas/v2."""
    return {
        "$schema": PCM_SCHEMA_URL,
        "name": PACKAGE_NAME,
        "description": PACKAGE_DESCRIPTION,
        "description_full": PACKAGE_DESCRIPTION_FULL,
        "identifier": PACKAGE_IDENTIFIER,
        "type": "plugin",
        "author": {"name": "MBrahim", "contact": {}},
        "license": "GPL-3.0-or-later",
        "resources": {
            "Homepage": "https://github.com/MBrahim/CubeMX-KiCad-Netlabels",
            "Source": "https://github.com/MBrahim/CubeMX-KiCad-Netlabels",
            "Issues": "https://github.com/MBrahim/CubeMX-KiCad-Netlabels/issues",
        },
        "versions": [
            {
                "version": version,
                "status": "testing",
                "runtime": "ipc",
                "kicad_version": "10.0",
            }
        ],
    }


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _plugin_files(project_root: Path) -> list[tuple[Path, Path]]:
    """Return the plugin files in KiCad's documented archive layout."""
    plugin_root = project_root / "kicad_plugin"
    files = [
        (plugin_root / source, Path("plugins") / source.name)
        for source in PLUGIN_FILES
    ]
    package_root = project_root / PACKAGE_MODULE
    if not package_root.is_dir():
        raise FileNotFoundError(f"Python package directory is missing: {package_root}")
    for source in sorted(package_root.glob("*.py")):
        if source.is_file():
            relative = source.relative_to(package_root)
            files.append((source, Path("plugins") / PACKAGE_MODULE / relative))
    for source, _ in files:
        if not source.is_file():
            raise FileNotFoundError(f"Required plugin source file is missing: {source}")
    return files


def _validate_pcm_icon(icon_path: Path) -> None:
    """Require KiCad's documented 64x64 PCM icon asset."""
    with icon_path.open("rb") as icon_file:
        header = icon_file.read(24)
    if (
        len(header) < 24
        or header[:8] != b"\x89PNG\r\n\x1a\n"
        or header[12:16] != b"IHDR"
    ):
        raise ValueError(f"PCM icon is not a valid PNG: {icon_path}")
    width, height = struct.unpack(">II", header[16:24])
    if (width, height) != (64, 64):
        raise ValueError(
            f"PCM icon must be 64x64 pixels, got {width}x{height}: {icon_path}"
        )


def build_package(
    project_root: Path,
    output_dir: Path,
    version: str,
    download_url: str | None = None,
) -> tuple[Path, Path]:
    """Build the PCM ZIP and submission metadata per KiCad's add-on format.

    Format: https://dev-docs.kicad.org/en/addons/
    """
    if not re.fullmatch(r"\d{1,4}(?:\.\d{1,4}(?:\.\d{1,6})?)?", version):
        raise ValueError(f"Invalid PCM package version: {version}")

    pcm_schema = _load_schema(PCM_SCHEMA_URL)
    plugin_schema = _load_schema(PLUGIN_SCHEMA_URL)
    metadata = _metadata(version)
    plugin_manifest = json.loads(
        (project_root / "kicad_plugin" / "plugin.json").read_text(encoding="utf-8")
    )
    pcm_icon = project_root / "kicad_plugin" / PCM_ICON
    _validate_pcm_icon(pcm_icon)
    validate(instance=metadata, schema=pcm_schema)
    validate(instance=plugin_manifest, schema=plugin_schema)

    output_dir.mkdir(parents=True, exist_ok=True)
    archive_path = output_dir / f"cubemx-kicad-netlabels-{version}.zip"
    submit_metadata_path = output_dir / "metadata.submit.json"
    plugin_files = _plugin_files(project_root)

    with zipfile.ZipFile(
        archive_path,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
    ) as archive:
        for source, archive_name in plugin_files:
            archive.write(source, archive_name.as_posix())
        archive.write(pcm_icon, PCM_ICON.as_posix())
        archive.writestr(
            "metadata.json",
            json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        )

    submit_metadata = json.loads(json.dumps(metadata))
    package_version = submit_metadata["versions"][0]
    package_version.update(
        {
            "download_url": download_url
            or GITHUB_RELEASE_URL.format(version=version),
            "download_sha256": hashlib.sha256(archive_path.read_bytes()).hexdigest(),
            "download_size": archive_path.stat().st_size,
            "install_size": _archive_install_size(archive_path),
        }
    )
    validate(instance=submit_metadata, schema=pcm_schema)
    _write_json(submit_metadata_path, submit_metadata)
    return archive_path, submit_metadata_path


def _archive_install_size(archive_path: Path) -> int:
    with zipfile.ZipFile(archive_path) as archive:
        return sum(info.file_size for info in archive.infolist())


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build and validate a KiCad PCM package archive."
    )
    parser.add_argument("--version", help="Package version (defaults to pyproject.toml)")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "dist",
        help="Directory for the archive and metadata.submit.json",
    )
    parser.add_argument(
        "--download-url",
        help="Direct download URL to include in metadata.submit.json",
    )
    args = parser.parse_args()
    version = args.version or _project_version(PROJECT_ROOT)
    archive_path, submit_metadata_path = build_package(
        PROJECT_ROOT,
        args.output_dir,
        version,
        args.download_url,
    )
    print(f"Created {archive_path}")
    print(f"Created {submit_metadata_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
