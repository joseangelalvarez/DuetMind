import unittest
import json

from duetmind.agents import AgentProfile, ProviderAgentAdapter
from duetmind.models import AgentId
from duetmind.providers import ProviderResponse, StaticInferenceProvider


class NoisyStaticProvider(StaticInferenceProvider):
    def complete(self, request):
        payload = {
            "fase_id": request.phase_id,
            "iteracion": request.iteration,
            "emisor": request.role,
            "grafo_estado": {
                "provider": self.provider_name,
                "role": request.role,
                "suffix": self.suffix,
                "status": "ok",
            },
            "alertas": [],
            "confianza": 0.8,
            "telemetria": {
                "vram_actual_gb": 0.0,
                "tiempo_ejecucion_ms": 100,
                "tokens_consumidos": 64,
                "timeout_flag": False,
                "oom_flag": False,
            },
        }
        return ProviderResponse(raw_text=json.dumps(payload), provider_name=self.provider_name)


class CompactStaticProvider(StaticInferenceProvider):
    def complete(self, request):
        payload = {
            "fase_id": request.phase_id,
            "iteracion": request.iteration,
            "emisor": request.role,
            "grafo_estado": {
                "intent_anchor": "demo intent",
                f"phase_{request.phase_id}_iter_{request.iteration}": self.suffix,
                f"phase_{request.phase_id}_iter_{request.iteration}_{request.role}": self.suffix,
            },
            "alertas": [],
            "confianza": 0.8,
            "telemetria": {
                "vram_actual_gb": 0.0,
                "tiempo_ejecucion_ms": 100,
                "tokens_consumidos": 64,
                "timeout_flag": False,
                "oom_flag": False,
            },
        }
        return ProviderResponse(raw_text=json.dumps(payload), provider_name=self.provider_name)


class TestProviderAgents(unittest.TestCase):
    def test_provider_agent_generates_valid_message(self) -> None:
        provider = StaticInferenceProvider("local-static", "proposal_yagni")
        adapter = ProviderAgentAdapter(
            AgentId.A,
            AgentProfile(
                name="Pragmatic_YAGNI_Engineer",
                role="pragmatic",
                base_confidence=0.78,
                tokens_per_call=420,
                latency_ms=900,
                proposal_suffix="proposal_yagni",
            ),
            provider,
        )
        message = adapter.generate(1, 1, {"intent": "demo"}, "demo intent")
        self.assertEqual(message.emisor, AgentId.A)
        self.assertIn("intent_anchor", message.grafo_estado)
        self.assertEqual(message.fase_id, 1)

    def test_discarded_keys_generate_defensive_alert(self) -> None:
        provider = NoisyStaticProvider("local-static", "proposal_yagni")
        adapter = ProviderAgentAdapter(
            AgentId.A,
            AgentProfile(
                name="Pragmatic_YAGNI_Engineer",
                role="pragmatic",
                base_confidence=0.78,
                tokens_per_call=420,
                latency_ms=900,
                proposal_suffix="proposal_yagni",
            ),
            provider,
        )
        message = adapter.generate(1, 1, {"intent": "demo", "legacy": "x"}, "demo intent")
        self.assertTrue(any(alert.invariante_violada == "keys_discarded_from_llm_output" for alert in message.alertas))

    def test_no_alert_when_no_keys_discarded(self) -> None:
        provider = CompactStaticProvider("local-static", "proposal_yagni")
        adapter = ProviderAgentAdapter(
            AgentId.A,
            AgentProfile(
                name="Pragmatic_YAGNI_Engineer",
                role="pragmatic",
                base_confidence=0.78,
                tokens_per_call=420,
                latency_ms=900,
                proposal_suffix="proposal_yagni",
            ),
            provider,
        )
        message = adapter.generate(1, 1, {}, "demo intent")
        self.assertFalse(any(alert.invariante_violada == "keys_discarded_from_llm_output" for alert in message.alertas))


if __name__ == "__main__":
    unittest.main()
