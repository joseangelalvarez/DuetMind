import unittest

from pydantic import ValidationError

from duetmind.mec import (
    MecAssetDescriptor,
    MecDaemonEndpoint,
    MecDeploymentArtifact,
    MecPhaseControl,
    MecProjectIdentity,
    MecPromptEnvelope,
    MecRuntimeManifest,
    RuntimePlatform,
)


class TestMecContracts(unittest.TestCase):
    def test_asset_requires_valid_sha256(self) -> None:
        with self.assertRaises(ValidationError):
            MecAssetDescriptor(asset_id="a1", sha256="bad-hash", size_bytes=1, media_type="application/bin")

    def test_phase_is_bounded_to_12(self) -> None:
        with self.assertRaises(ValidationError):
            MecPhaseControl(phase_id=13, iteration=1, max_iterations=4)

    def test_runtime_manifest_rejects_duplicate_assets(self) -> None:
        with self.assertRaises(ValidationError):
            MecRuntimeManifest(
                identity=MecProjectIdentity(
                    project_id="11111111-1111-4111-8111-111111111111",
                    tenant_id="tenant-main",
                    schema_version="v1.4",
                ),
                phase_control=MecPhaseControl(phase_id=1, iteration=1, max_iterations=4),
                prompt=MecPromptEnvelope(prompt_id="p1", role="A", intent="demo intent", token_budget=2048),
                security={"allow_hosts": ["127.0.0.1"], "api_key_required": True, "max_payload_kb": 256},
                daemons=[MecDaemonEndpoint(daemon_name="ollama", host="127.0.0.1", port=11434)],
                assets=[
                    {
                        "asset_id": "model-1",
                        "sha256": "a" * 64,
                        "size_bytes": 10,
                        "media_type": "application/gguf",
                    },
                    {
                        "asset_id": "model-1",
                        "sha256": "b" * 64,
                        "size_bytes": 20,
                        "media_type": "application/gguf",
                    },
                ],
                deployment=MecDeploymentArtifact(
                    platform=RuntimePlatform.WINDOWS,
                    artifact_name="backend_core.exe",
                    artifact_sha256="c" * 64,
                    executable_size_bytes=1024,
                ),
            )


if __name__ == "__main__":
    unittest.main()
