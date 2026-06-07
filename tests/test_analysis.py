import unittest

from duetmind.analysis import assess_go_no_go


class TestAnalysis(unittest.TestCase):
    def test_assess_go_no_go_returns_go_for_strong_results(self) -> None:
        assessment = assess_go_no_go(
            [
                {"phase_id": 1, "phase_name": "Concepcion", "environment": "cloud", "model_tier": "advanced", "signal": "CONGELAR_Y_AVANZAR", "score": 8.4, "reason": "ok"},
                {"phase_id": 2, "phase_name": "Arquitectura", "environment": "local", "model_tier": "quantized", "signal": "CONVERGE_CONDICIONADO", "score": 8.2, "reason": "ok"},
                {"phase_id": 3, "phase_name": "Cierre", "environment": "cloud", "model_tier": "audit", "signal": "CONGELAR_Y_AVANZAR", "score": 8.8, "reason": "ok"},
                {"phase_id": 4, "phase_name": "Cierre", "environment": "cloud", "model_tier": "audit", "signal": "CONGELAR_Y_AVANZAR", "score": 8.5, "reason": "ok"},
                {"phase_id": 5, "phase_name": "Cierre", "environment": "cloud", "model_tier": "audit", "signal": "CONGELAR_Y_AVANZAR", "score": 8.6, "reason": "ok"},
                {"phase_id": 6, "phase_name": "Cierre", "environment": "cloud", "model_tier": "audit", "signal": "CONGELAR_Y_AVANZAR", "score": 8.7, "reason": "ok"},
                {"phase_id": 7, "phase_name": "Cierre", "environment": "cloud", "model_tier": "audit", "signal": "CONGELAR_Y_AVANZAR", "score": 8.3, "reason": "ok"},
                {"phase_id": 8, "phase_name": "Cierre", "environment": "cloud", "model_tier": "audit", "signal": "CONGELAR_Y_AVANZAR", "score": 8.1, "reason": "ok"},
                {"phase_id": 9, "phase_name": "Cierre", "environment": "cloud", "model_tier": "audit", "signal": "CONGELAR_Y_AVANZAR", "score": 8.0, "reason": "ok"},
                {"phase_id": 10, "phase_name": "Cierre", "environment": "cloud", "model_tier": "audit", "signal": "CONGELAR_Y_AVANZAR", "score": 8.4, "reason": "ok"},
                {"phase_id": 11, "phase_name": "Cierre", "environment": "cloud", "model_tier": "audit", "signal": "CONGELAR_Y_AVANZAR", "score": 8.2, "reason": "ok"},
                {"phase_id": 12, "phase_name": "Cierre", "environment": "cloud", "model_tier": "audit", "signal": "CONGELAR_Y_AVANZAR", "score": 8.6, "reason": "ok"},
            ]
        )

        self.assertTrue(assessment.can_analyze)
        self.assertEqual(assessment.decision, "GO")
        self.assertEqual(assessment.final_signal, "CONGELAR_Y_AVANZAR")
        self.assertEqual(assessment.blocking_signals, [])

    def test_assess_go_no_go_rejects_blockers(self) -> None:
        assessment = assess_go_no_go(
            [
                {"phase_id": 1, "phase_name": "Concepcion", "environment": "cloud", "model_tier": "advanced", "signal": "ESCALAR_A_HUMANO", "score": 4.0, "reason": "stop"},
            ]
        )

        self.assertTrue(assessment.can_analyze)
        self.assertEqual(assessment.decision, "NO_GO")
        self.assertIn("blocking_signal_detected", assessment.reasons)

    def test_assess_go_no_go_returns_conditional_for_partial_completion(self) -> None:
        assessment = assess_go_no_go(
            [
                {"phase_id": 1, "phase_name": "Concepcion", "environment": "cloud", "model_tier": "advanced", "signal": "CONGELAR_Y_AVANZAR", "score": 8.4, "reason": "ok"},
                {"phase_id": 2, "phase_name": "Arquitectura", "environment": "local", "model_tier": "quantized", "signal": "CONVERGE_CONDICIONADO", "score": 8.1, "reason": "ok"},
                {"phase_id": 3, "phase_name": "Cierre", "environment": "cloud", "model_tier": "audit", "signal": "CONGELAR_Y_AVANZAR", "score": 8.2, "reason": "ok"},
            ]
        )

        self.assertTrue(assessment.can_analyze)
        self.assertEqual(assessment.decision, "GO_CONDICIONAL")
        self.assertIn("incomplete_phase_coverage", assessment.reasons)


if __name__ == "__main__":
    unittest.main()