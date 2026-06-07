import unittest

from duetmind.prompts import PromptLibrary


class TestPrompts(unittest.TestCase):
    def test_prompt_render_includes_phase_and_intent(self) -> None:
        library = PromptLibrary()
        rendered = library.render(1, "Crear sistema seguro")
        self.assertIn("PHASE_ID=1", rendered)
        self.assertIn("USER_INTENT=Crear sistema seguro", rendered)
        self.assertIn("OUTPUT_POLICY=JSON_COMPACT_ONLY", rendered)


if __name__ == "__main__":
    unittest.main()
