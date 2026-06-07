import unittest

from pydantic import BaseModel

from duetmind.middleware import parse_with_layered_repair, structural_delta_ratio


class Payload(BaseModel):
    name: str
    count: int


class TestMiddleware(unittest.TestCase):
    def test_repair_truncated_json(self) -> None:
        raw = '{"name": "alpha", "count": 3...'
        parsed = parse_with_layered_repair(raw, Payload)
        self.assertEqual(parsed.name, "alpha")
        self.assertEqual(parsed.count, 3)

    def test_structural_delta_detects_change(self) -> None:
        prev = {"a": "1", "b": "2"}
        new = {"a": "1", "b": "3"}
        delta = structural_delta_ratio(prev, new)
        self.assertGreater(delta, 0.0)


if __name__ == "__main__":
    unittest.main()
