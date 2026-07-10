import sys
import types
import unittest
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

sys.modules.setdefault("app.db", types.SimpleNamespace(execute_select=lambda *args, **kwargs: []))
sys.modules.setdefault(
    "app.services.openai_service",
    types.SimpleNamespace(
        answer_with_kpis=lambda *args, **kwargs: None,
        has_openai_key=lambda: False,
        summarize_with_openai=lambda *args, **kwargs: None,
    ),
)
sys.modules.setdefault(
    "app.services.periods",
    types.SimpleNamespace(parse_period=lambda question, data_inicio=None, data_fim=None: {"data_inicio": data_inicio, "data_fim": data_fim}),
)
sys.modules.setdefault("app.services.semantic", types.SimpleNamespace(find_question_route=lambda question: {"status": "needs_ai"}))
sys.modules.setdefault(
    "app.sql_guard",
    types.SimpleNamespace(is_safe_select=lambda sql: True, template_to_psycopg=lambda sql: sql),
)

from app.services.question_answering import (  # noqa: E402
    answer_out_of_scope,
    is_clear_out_of_scope_question,
    is_pharmacy_business_scope,
)


class AiScopePolicyTest(unittest.TestCase):
    def test_blocks_clearly_unrelated_questions(self):
        blocked_questions = [
            "Qual a origem da vida?",
            "Quem ganhou a segunda guerra mundial?",
            "Qual meu horoscopo de hoje?",
            "Qual o placar do jogo de futebol?",
        ]

        for question in blocked_questions:
            with self.subTest(question=question):
                self.assertTrue(is_clear_out_of_scope_question(question))

    def test_allows_pharmacy_business_questions(self):
        allowed_questions = [
            "Como posso crescer minha farmacia?",
            "Crie campanhas de marketing para minha farmacia",
            "Como melhorar atendimento no balcao?",
            "Como aumentar o ticket medio da loja?",
            "Quais produtos devo priorizar no bairro?",
        ]

        for question in allowed_questions:
            with self.subTest(question=question):
                self.assertTrue(is_pharmacy_business_scope(question))
                self.assertFalse(is_clear_out_of_scope_question(question))

    def test_scope_answer_is_polite_and_tagged(self):
        result = answer_out_of_scope("Qual a origem da vida?", None, None)

        self.assertEqual(result["status"], "answered")
        self.assertEqual(result["route"]["status"], "scope_blocked")
        self.assertIn("foge do escopo", result["answer"])
        self.assertIn("farmacias", result["answer"])


if __name__ == "__main__":
    unittest.main()
