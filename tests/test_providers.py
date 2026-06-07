import unittest

from duetmind.providers import ProviderRequest, StaticInferenceProvider


class TestProviders(unittest.TestCase):
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
