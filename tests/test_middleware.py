import unittest

from pydantic import BaseModel

from duetmind.middleware import parse_with_layered_repair, structural_delta_ratio
from duetmind.models import AgentId, CompactAgentMessage


class Payload(BaseModel):
    name: str
    count: int


class TestMiddleware(unittest.TestCase):
    def test_repair_truncated_json(self) -> None:
        raw = '{"name": "alpha", "count": 3...'
        parsed = parse_with_layered_repair(raw, Payload)
        self.assertEqual(parsed.name, "alpha")
        self.assertEqual(parsed.count, 3)

    def test_layer4_sentinel_on_no_json(self) -> None:
        raw = "this is not json"
        parsed = parse_with_layered_repair(
            raw,
            CompactAgentMessage,
            phase_id=3,
            iteration=2,
            agent_id=AgentId.A,
        )
        self.assertEqual(parsed.confianza, 0.0)
        self.assertTrue(parsed.alertas[0].es_bloqueante)
        self.assertEqual(parsed.fase_id, 3)
        self.assertEqual(parsed.iteracion, 2)

    def test_layer4_sentinel_on_all_layers_fail(self) -> None:
        raw = '{"fase_id": "not-int", "iteracion": "x"}'
        parsed = parse_with_layered_repair(
            raw,
            CompactAgentMessage,
            phase_id=1,
            iteration=1,
            agent_id=AgentId.B,
        )
        self.assertEqual(parsed.confianza, 0.0)
        self.assertTrue(parsed.alertas[0].es_bloqueante)
        self.assertEqual(parsed.emisor, AgentId.B)

    def test_extract_block_no_brace_returns_sentinel(self) -> None:
        parsed = parse_with_layered_repair(
            "plain text without braces",
            CompactAgentMessage,
            phase_id=5,
            iteration=1,
        )
        self.assertEqual(parsed.confianza, 0.0)
        self.assertEqual(parsed.grafo_estado.get("sentinel"), "parse_failure")
        self.assertEqual(parsed.emisor, AgentId.A)

    def test_single_quote_inside_string_not_corrupted(self) -> None:
        raw = '{"name": "o\'hara", "count": 7}'
        parsed = parse_with_layered_repair(raw, Payload)
        self.assertEqual(parsed.name, "o'hara")
        self.assertEqual(parsed.count, 7)

    def test_layer3_micro_repair_callback_can_fix_payload(self) -> None:
        raw = '{"name":"alpha","count":'

        def repairer(_: str) -> str:
            return '{"name":"alpha","count":9}'

        parsed = parse_with_layered_repair(raw, Payload, layer3_repairer=repairer)
        self.assertEqual(parsed.name, "alpha")
        self.assertEqual(parsed.count, 9)

    def test_structural_delta_detects_change(self) -> None:
        prev = {"a": "1", "b": "2"}
        new = {"a": "1", "b": "3"}
        delta = structural_delta_ratio(prev, new)
        self.assertGreater(delta, 0.0)


if __name__ == "__main__":
    unittest.main()
