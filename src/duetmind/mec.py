from __future__ import annotations

import re
from enum import Enum

from pydantic import BaseModel, Field, field_validator


SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


class RuntimePlatform(str, Enum):
    WINDOWS = "windows"
    LINUX = "linux"


class PromptRole(str, Enum):
    A = "A"
    B = "B"
    M = "M"


class MecProjectIdentity(BaseModel):
    project_id: str = Field(min_length=36, max_length=36)
    tenant_id: str = Field(min_length=3, max_length=64)
    schema_version: str = Field(pattern=r"^v\d+\.\d+$")

    @field_validator("project_id")
    @classmethod
    def validate_project_id(cls, value: str) -> str:
        if UUID_RE.match(value) is None:
            raise ValueError("project_id must be UUID v1-v5")
        return value


class MecPhaseControl(BaseModel):
    phase_id: int = Field(ge=1, le=12)
    iteration: int = Field(ge=1, le=32)
    max_iterations: int = Field(ge=1, le=32)

    @field_validator("max_iterations")
    @classmethod
    def validate_iteration_window(cls, value: int) -> int:
        if value < 1:
            raise ValueError("max_iterations must be at least 1")
        return value


class MecAssetDescriptor(BaseModel):
    asset_id: str = Field(min_length=3, max_length=128)
    sha256: str
    size_bytes: int = Field(gt=0)
    media_type: str = Field(min_length=3, max_length=64)

    @field_validator("sha256")
    @classmethod
    def validate_sha256(cls, value: str) -> str:
        normalized = value.lower()
        if SHA256_RE.match(normalized) is None:
            raise ValueError("sha256 must be 64 lowercase hex chars")
        return normalized


class MecSecurityPolicy(BaseModel):
    allow_hosts: list[str] = Field(min_length=1, max_length=16)
    api_key_required: bool = True
    max_payload_kb: int = Field(ge=1, le=10240)

    @field_validator("allow_hosts")
    @classmethod
    def validate_hosts(cls, value: list[str]) -> list[str]:
        for host in value:
            if not host or len(host) > 255:
                raise ValueError("allow_hosts includes invalid hostname")
        return value


class MecPromptEnvelope(BaseModel):
    prompt_id: str = Field(min_length=3, max_length=64)
    role: PromptRole
    intent: str = Field(min_length=3, max_length=5000)
    token_budget: int = Field(ge=64, le=200000)


class MecAgentOutput(BaseModel):
    emitter: PromptRole
    confidence: float = Field(ge=0.0, le=1.0)
    graph_state: dict[str, str] = Field(min_length=1, max_length=256)
    blocking_alerts: int = Field(ge=0, le=64)


class MecTelemetryBudget(BaseModel):
    tokens_consumed: int = Field(ge=0)
    latency_ms: int = Field(ge=0, le=120000)
    timeout_flag: bool = False
    oom_flag: bool = False


class MecConsensusDecision(BaseModel):
    agreement: float = Field(ge=0.0, le=1.0)
    stability: float = Field(ge=0.0, le=1.0)
    risk: float = Field(ge=0.0, le=1.0)
    score: float = Field(ge=0.0, le=10.0)
    signal: str = Field(min_length=3, max_length=64)


class MecLedgerBlock(BaseModel):
    block_id: str = Field(min_length=36, max_length=36)
    previous_hash: str
    manifest_hash: str
    created_at_epoch: float = Field(gt=0)

    @field_validator("block_id")
    @classmethod
    def validate_block_id(cls, value: str) -> str:
        if UUID_RE.match(value) is None:
            raise ValueError("block_id must be UUID v1-v5")
        return value

    @field_validator("previous_hash", "manifest_hash")
    @classmethod
    def validate_hashes(cls, value: str) -> str:
        normalized = value.lower()
        if SHA256_RE.match(normalized) is None:
            raise ValueError("ledger hashes must be SHA-256")
        return normalized


class MecDaemonEndpoint(BaseModel):
    daemon_name: str = Field(min_length=2, max_length=64)
    host: str = Field(default="127.0.0.1")
    port: int = Field(ge=1024, le=65535)
    protocol: str = Field(default="http", pattern=r"^(http|https)$")


class MecDeploymentArtifact(BaseModel):
    platform: RuntimePlatform
    artifact_name: str = Field(min_length=3, max_length=128)
    artifact_sha256: str
    executable_size_bytes: int = Field(gt=0)

    @field_validator("artifact_sha256")
    @classmethod
    def validate_artifact_hash(cls, value: str) -> str:
        normalized = value.lower()
        if SHA256_RE.match(normalized) is None:
            raise ValueError("artifact_sha256 must be SHA-256")
        return normalized


class MecRuntimeManifest(BaseModel):
    identity: MecProjectIdentity
    phase_control: MecPhaseControl
    prompt: MecPromptEnvelope
    security: MecSecurityPolicy
    daemons: list[MecDaemonEndpoint] = Field(min_length=1, max_length=8)
    assets: list[MecAssetDescriptor] = Field(min_length=1, max_length=2048)
    deployment: MecDeploymentArtifact

    @field_validator("assets")
    @classmethod
    def validate_distinct_asset_ids(cls, value: list[MecAssetDescriptor]) -> list[MecAssetDescriptor]:
        ids = {asset.asset_id for asset in value}
        if len(ids) != len(value):
            raise ValueError("assets contain duplicated asset_id")
        return value
