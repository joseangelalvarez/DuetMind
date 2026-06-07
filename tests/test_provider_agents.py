import unittest

from duetmind.agents import AgentProfile, ProviderAgentAdapter
from duetmind.models import AgentId
from duetmind.providers import StaticInferenceProvider


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


if __name__ == "__main__":
    unittest.main()
