from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path


class PackagingPlatform(str, Enum):
    WINDOWS = "windows"
    LINUX = "linux"


@dataclass(frozen=True)
class PackagingAsset:
    source: str
    destination: str


@dataclass(frozen=True)
class BackendPackagingPlan:
    platform: PackagingPlatform
    app_name: str
    entry_point: str
    dist_path: str
    build_path: str
    spec_name: str
    hidden_imports: list[str]
    data_files: list[PackagingAsset]
    pathex: list[str]


def build_backend_packaging_plan(platform: PackagingPlatform = PackagingPlatform.WINDOWS) -> BackendPackagingPlan:
    app_name = "backend_core.exe" if platform == PackagingPlatform.WINDOWS else "backend_core"
    spec_name = "backend_core.spec"
    return BackendPackagingPlan(
        platform=platform,
        app_name=app_name,
        entry_point="src/duetmind/main.py",
        dist_path="dist/backend",
        build_path="build/backend",
        spec_name=spec_name,
        hidden_imports=[
            "duetmind.analysis",
            "duetmind.agents",
            "duetmind.distribution",
            "duetmind.exceptions",
            "duetmind.fsm",
            "duetmind.infra",
            "duetmind.mec",
            "duetmind.middleware",
            "duetmind.moderator",
            "duetmind.orchestrator",
            "duetmind.pipeline",
            "duetmind.providers",
            "duetmind.scoring",
            "duetmind.semantic",
            "duetmind.server",
            "duetmind.storage",
        ],
        data_files=[
            PackagingAsset("README.md", "README.md"),
            PackagingAsset("pyproject.toml", "pyproject.toml"),
        ],
        pathex=["src"],
    )


def render_backend_spec(plan: BackendPackagingPlan) -> str:
    hidden_imports = ",\n        ".join(repr(item) for item in plan.hidden_imports)
    datas = ",\n        ".join(
        f"({asset.source!r}, {asset.destination!r})" for asset in plan.data_files
    )
    return f'''# -*- mode: python ; coding: utf-8 -*-
block_cipher = None

a = Analysis(
    ['{plan.entry_point}'],
    pathex={plan.pathex!r},
    binaries=[],
    datas=[
        {datas}
    ],
    hiddenimports=[
        {hidden_imports}
    ],
    hookspath=[],
    hooksconfig={{}},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='{plan.app_name}',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
)
'''


def write_backend_spec(path: str | Path, plan: BackendPackagingPlan) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_backend_spec(plan), encoding="utf-8")


def render_backend_packaging_manifest_json(plan: BackendPackagingPlan) -> str:
    return json.dumps(asdict(plan), indent=2, sort_keys=True)


def write_backend_packaging_manifest(path: str | Path, plan: BackendPackagingPlan) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_backend_packaging_manifest_json(plan), encoding="utf-8")


def prepare_backend_packaging_staging(root_dir: str | Path, plan: BackendPackagingPlan | None = None) -> Path:
    root = Path(root_dir)
    root.mkdir(parents=True, exist_ok=True)

    plan = plan or build_backend_packaging_plan()
    tree = [
        root,
        root / "build",
        root / "build" / "backend",
        root / "dist",
        root / "dist" / "backend",
    ]
    for directory in tree:
        directory.mkdir(parents=True, exist_ok=True)

    write_backend_spec(root / plan.spec_name, plan)
    write_backend_packaging_manifest(root / "backend-packaging-manifest.json", plan)

    build_script = root / ("build-backend.ps1" if plan.platform == PackagingPlatform.WINDOWS else "build-backend.sh")
    if plan.platform == PackagingPlatform.WINDOWS:
        build_script.write_text(
            f"Set-Location $PSScriptRoot\npyinstaller --noconfirm --clean {plan.spec_name}\n",
            encoding="utf-8",
        )
    else:
        build_script.write_text(
            f"#!/usr/bin/env sh\nset -e\npyinstaller --noconfirm --clean {plan.spec_name}\n",
            encoding="utf-8",
        )
    return root
