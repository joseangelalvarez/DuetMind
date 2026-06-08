import unittest

from duetmind.providers import OllamaInferenceProvider, ProviderRequest, StaticInferenceProvider


class TestProviders(unittest.TestCase):
    def test_ollama_provider_retries_before_fallback(self) -> None:
        attempts = {"count": 0}

        def flaky_transport(_url, _payload, _timeout):
            attempts["count"] += 1
            if attempts["count"] < 3:
                raise RuntimeError("temporary_failure")
            return {
                "response": '{"fase_id":1,"iteracion":1,"emisor":"A","grafo_estado":{"semantic":"ok_after_retry"},"alertas":[],"confianza":0.8,"telemetria":{"vram_actual_gb":0.0,"tiempo_ejecucion_ms":10,"tokens_consumidos":10,"timeout_flag":false,"oom_flag":false}}'
            }

        provider = OllamaInferenceProvider(
            model="llama3.1:8b",
            transport=flaky_transport,
            max_retries=3,
            initial_backoff_s=0.0,
        )
        response = provider.complete(
            ProviderRequest(phase_id=1, iteration=1, role="A", prompt_text="demo")
        )

        self.assertEqual(attempts["count"], 3)
        self.assertIn('"ok_after_retry"', response.raw_text)

    def test_ollama_provider_returns_transport_response(self) -> None:
        def transport(_url, _payload, _timeout):
            return {
                "response": '{"fase_id":1,"iteracion":1,"emisor":"A","grafo_estado":{"semantic":"demo"},"alertas":[],"confianza":0.8,"telemetria":{"vram_actual_gb":0.0,"tiempo_ejecucion_ms":10,"tokens_consumidos":10,"timeout_flag":false,"oom_flag":false}}'
            }

        provider = OllamaInferenceProvider(model="llama3.1:8b", transport=transport)
        response = provider.complete(
            ProviderRequest(phase_id=1, iteration=1, role="A", prompt_text="demo")
        )

        self.assertEqual(response.provider_name, "ollama")
        self.assertIn('"semantic":"demo"', response.raw_text)

    def test_ollama_provider_fallback_when_transport_fails(self) -> None:
        def failing_transport(_url, _payload, _timeout):
            raise RuntimeError("network_down")

        provider = OllamaInferenceProvider(model="llama3.1:8b", transport=failing_transport)
        response = provider.complete(
            ProviderRequest(phase_id=1, iteration=1, role="A", prompt_text="demo")
        )

        self.assertIn(":fallback", response.provider_name)
        self.assertIn('"status": "fallback"', response.raw_text)

    def test_static_provider_returns_json_payload(self) -> None:
        provider = StaticInferenceProvider("local-static", "proposal")
        response = provider.complete(
            ProviderRequest(phase_id=1, iteration=1, role="A", prompt_text="demo")
        )
        self.assertEqual(response.provider_name, "local-static")
        self.assertIn('"fase_id": 1', response.raw_text)
        self.assertIn('"suffix": "proposal"', response.raw_text)


if __name__ == "__main__":
    unittest.main()
