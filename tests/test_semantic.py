import unittest

from duetmind.semantic import SemanticDriftAnalyzer


class FakeEncoder:
    def __init__(self, vectors):
        self.vectors = vectors

    def encode(self, texts, normalize_embeddings=True):
        return self.vectors


class TestSemanticDriftAnalyzer(unittest.TestCase):
    def test_fallback_distance_is_low_for_identical_text(self) -> None:
        analyzer = SemanticDriftAnalyzer(auto_load=False)
        self.assertAlmostEqual(analyzer.distance("alpha beta", "alpha beta"), 0.0, places=6)

    def test_embedding_distance_uses_encoder(self) -> None:
        analyzer = SemanticDriftAnalyzer(
            encoder=FakeEncoder([[1.0, 0.0], [0.0, 1.0]]),
            auto_load=False,
        )
        self.assertAlmostEqual(analyzer.distance("a", "b"), 1.0, places=6)


if __name__ == "__main__":
    unittest.main()
