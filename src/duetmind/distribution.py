from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from enum import Enum
from pathlib import Path


class DistributionPlatform(str, Enum):
    WINDOWS = "windows"
    LINUX = "linux"


@dataclass(frozen=True)
class DistributionArtifact:
    name: str
    relative_path: str
    description: str


@dataclass(frozen=True)
class DistributionManifest:
    platform: DistributionPlatform
    root_name: str
    launcher: DistributionArtifact
    backend: DistributionArtifact
    database: DistributionArtifact
    engines: list[DistributionArtifact]
    models: list[DistributionArtifact]
    workspace_root: DistributionArtifact


def build_distribution_manifest(platform: DistributionPlatform = DistributionPlatform.WINDOWS) -> DistributionManifest:
    root_name = "MiAplicacionAudiovisual"
    launcher_name = "launcher.exe" if platform == DistributionPlatform.WINDOWS else "launcher"
    backend_name = "backend_core.exe" if platform == DistributionPlatform.WINDOWS else "backend_core"

    return DistributionManifest(
        platform=platform,
        root_name=root_name,
        launcher=DistributionArtifact(
            name=launcher_name,
            relative_path=launcher_name,
            description="Frontend launcher compiled with Tauri",
        ),
        backend=DistributionArtifact(
            name=backend_name,
            relative_path=f"resources/{backend_name}",
            description="FastAPI backend with FSM, ledger and orchestration core",
        ),
        database=DistributionArtifact(
            name="database.sqlite",
            relative_path="resources/database.sqlite",
            description="Self-contained SQLite persistence",
        ),
        engines=[
            DistributionArtifact(
                name="ollama",
                relative_path="resources/engines/ollama/",
                description="Portable Ollama runtime",
            ),
            DistributionArtifact(
                name="comfyui",
                relative_path="resources/engines/comfyui/",
                description="Portable ComfyUI runtime",
            ),
        ],
        models=[
            DistributionArtifact(
                name="llm",
                relative_path="resources/models/llm/",
                description="Quantized text-generation models",
            ),
            DistributionArtifact(
                name="diffusion",
                relative_path="resources/models/diffusion/",
                description="Image/diffusion model checkpoints",
            ),
        ],
        workspace_root=DistributionArtifact(
            name="workspace",
            relative_path="workspace/",
            description="User project workspace root",
        ),
    )


def render_distribution_manifest_json(manifest: DistributionManifest) -> str:
    return json.dumps(asdict(manifest), indent=2, sort_keys=True)


def write_distribution_manifest(path: str | Path, manifest: DistributionManifest) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_distribution_manifest_json(manifest), encoding="utf-8")


def prepare_distribution_staging(root_dir: str | Path, manifest: DistributionManifest | None = None) -> Path:
    root = Path(root_dir)
    root.mkdir(parents=True, exist_ok=True)

    manifest = manifest or build_distribution_manifest()
    tree = [
        root,
        root / "resources",
        root / "resources" / "engines",
        root / "resources" / "engines" / "ollama",
        root / "resources" / "engines" / "comfyui",
        root / "resources" / "models",
        root / "resources" / "models" / "llm",
        root / "resources" / "models" / "diffusion",
        root / "workspace",
    ]
    for directory in tree:
        directory.mkdir(parents=True, exist_ok=True)

    write_distribution_manifest(root / "distribution-manifest.json", manifest)
    launcher_config = {
        "platform": manifest.platform.value,
        "launcher": manifest.launcher.relative_path,
        "backend": manifest.backend.relative_path,
        "database": manifest.database.relative_path,
        "health_endpoints": ["/health", "/history", "/bundle"],
        "event_channel": "PuertoEventos",
    }
    (root / "launcher-config.json").write_text(
        json.dumps(launcher_config, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return root
