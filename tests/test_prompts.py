import unittest

from duetmind.models import AgentId
from duetmind.prompts import PromptLibrary


class TestPrompts(unittest.TestCase):
    def test_prompt_render_includes_phase_and_intent(self) -> None:
        library = PromptLibrary()
        rendered = library.render(1, "Crear sistema seguro")
        self.assertIn("PHASE_ID=1", rendered)
        self.assertIn("USER_INTENT=Crear sistema seguro", rendered)
        self.assertIn("OUTPUT_POLICY=JSON_COMPACT_ONLY", rendered)

    def test_agent_a_and_b_receive_different_prompts(self) -> None:
        library = PromptLibrary()
        rendered_a = library.render(1, "Crear sistema seguro", AgentId.A)
        rendered_b = library.render(1, "Crear sistema seguro", AgentId.B)
        self.assertNotEqual(rendered_a, rendered_b)

    def test_render_backward_compatible_without_agent_id(self) -> None:
        library = PromptLibrary()
        rendered_default = library.render(1, "Crear sistema seguro")
        rendered_a = library.render(1, "Crear sistema seguro", AgentId.A)
        self.assertEqual(rendered_default, rendered_a)


if __name__ == "__main__":
    unittest.main()
