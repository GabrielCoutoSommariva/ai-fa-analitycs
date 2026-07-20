from datetime import date
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

from app.services import question_answering as qa  # noqa: E402


class AiLocalAnswersTest(unittest.TestCase):
    def setUp(self):
        self._execute_select = qa.execute_select
        self._execute_optional_select = qa.execute_optional_select

    def tearDown(self):
        qa.execute_select = self._execute_select
        qa.execute_optional_select = self._execute_optional_select

    def test_formula_followup_uses_registered_kpi_definition(self):
        result = qa.answer_formula("Como calculou?", "desconto_usuario", date(2026, 6, 1), date(2026, 7, 1))

        self.assertEqual(result["route"]["status"], "local_followup")
        self.assertIn("Desconto usuario", result["answer"])
        self.assertIn("analytics.mv_kpi_operacional_diario", result["answer"])

    def test_operational_discount_answer_uses_aggregated_percentage(self):
        def fake_execute_select(sql, params):
            self.assertIn("analytics.mv_kpi_operacional_diario", sql)
            self.assertIn("sum(desconto_manual) / sum(receita_liquida_item)", sql)
            return [
                {
                    "total_cupons": 100,
                    "cupons_um_item": 40,
                    "percentual_cupons_um_item": 0.4,
                    "desconto_manual": 650,
                    "desconto_automatico": 2300,
                    "desconto_total": 2950,
                    "receita_liquida_item": 10000,
                    "custo_total_estimado": 7000,
                    "percentual_desconto_manual": 0.065,
                    "percentual_desconto_automatico": 0.23,
                    "percentual_desconto_cmv": 0.4214285714,
                }
            ]

        qa.execute_select = fake_execute_select

        result = qa.answer_operational_kpi(
            "Qual meu desconto usuario?",
            date(2026, 6, 1),
            date(2026, 7, 1),
            None,
            ["12345678000199"],
            "desconto_usuario",
        )

        self.assertEqual(result["status"], "answered")
        self.assertEqual(result["route"]["intent"], "desconto_usuario")
        self.assertIn("6,50%", result["answer"])
        self.assertIn("R$ 650,00", result["answer"])
        self.assertIn("cnpjs", result["params"])

    def test_seasonality_answer_reads_versioned_mv(self):
        def fake_execute_optional_select(sql, params):
            self.assertIn("analytics.mv_ai_sazonalidade_dia_semana", sql)
            return [
                {"dia_semana": 5, "nome_dia_semana": "sexta-feira", "dias_analisados": 4, "cupons": 100, "faturamento": 20000, "ticket_medio": 200},
                {"dia_semana": 1, "nome_dia_semana": "segunda-feira", "dias_analisados": 4, "cupons": 80, "faturamento": 12000, "ticket_medio": 150},
            ]

        qa.execute_optional_select = fake_execute_optional_select

        result = qa.answer_seasonality("Qual melhor dia da semana?", date(2026, 6, 1), date(2026, 7, 1), None, None)

        self.assertEqual(result["route"]["intent"], "sazonalidade_dia_semana")
        self.assertIn("sexta-feira", result["answer"])
        self.assertIn("segunda-feira", result["answer"])

    def test_discounts_returns_answer_reads_new_daily_and_product_mvs(self):
        seen_sql = []

        def fake_execute_optional_select(sql, params):
            seen_sql.append(sql)
            if "mv_ai_desconto_devolucao_produto_mensal" in sql:
                return [
                    {
                        "produto_id": 1,
                        "produto": "Produto A",
                        "desconto_total": 100,
                        "valor_devolucao": 50,
                        "qtd_devolvida": 2,
                        "receita": 1000,
                    }
                ]
            if "group by data" in sql:
                return [{"data": date(2026, 6, 1), "faturamento": 1000, "desconto_total": 100, "valor_devolucao": 50}]
            return [
                {
                    "faturamento": 1000,
                    "cupons": 10,
                    "desconto_manual": 60,
                    "desconto_automatico": 40,
                    "desconto_total": 100,
                    "percentual_desconto": 0.1,
                    "valor_devolucao": 50,
                    "percentual_devolucao": 0.047619,
                }
            ]

        qa.execute_optional_select = fake_execute_optional_select

        result = qa.answer_discounts_returns("Analise descontos e devolucoes", date(2026, 6, 1), date(2026, 7, 1), None, None)

        self.assertEqual(result["route"]["intent"], "descontos_devolucoes")
        self.assertIn("10,00%", result["answer"])
        self.assertIn("Produto A", result["answer"])
        self.assertTrue(any("mv_ai_desconto_devolucao_diario" in sql for sql in seen_sql))
        self.assertTrue(any("mv_ai_desconto_devolucao_produto_mensal" in sql for sql in seen_sql))

    def test_network_revenue_comparison_uses_network_average_per_store(self):
        calls = []

        def fake_execute_select(sql, params):
            calls.append(params.copy())
            if "cnpjs" in params:
                return [{"faturamento": 1000, "cupons": 10, "lojas_com_faturamento": 1, "ticket_medio": 100, "faturamento_medio_loja": 1000}]
            return [{"faturamento": 3000, "cupons": 30, "lojas_com_faturamento": 3, "ticket_medio": 100, "faturamento_medio_loja": 1000}]

        qa.execute_select = fake_execute_select

        result = qa.answer_network_comparison(
            "E a rede?",
            date(2026, 6, 1),
            date(2026, 7, 1),
            None,
            ["12345678000199"],
            "faturamento",
        )

        self.assertEqual(result["route"]["topic"], "faturamento")
        self.assertIn("media por loja", result["answer"])
        self.assertIn("3 lojas", result["answer"])
        self.assertTrue(any("cnpjs" in call for call in calls))
        self.assertTrue(any("cnpjs" not in call for call in calls))

    def test_product_specific_sales_answer_uses_item_route(self):
        def fake_execute_select(sql, params):
            self.assertIn("bronze.vendas_item", sql)
            self.assertIn("bronze.vendas_cab", sql)
            self.assertEqual(params["produto_codigo"], "7896018751002")
            return [
                {
                    "produtos_encontrados": 1,
                    "produto_id": 41741,
                    "id_produto_interno": 41741,
                    "ean_gtin": "7896018751002",
                    "produto": "Produto Teste",
                    "quantidade_vendida": 12,
                    "valor_total_vendido_item": 1200,
                    "cmv_estimado_item": 700,
                    "lucro_bruto_item": 500,
                    "margem_item": 0.4166667,
                    "quantidade_cupons_com_item": 10,
                    "valor_total_cupons_com_item": 2500,
                }
            ]

        qa.execute_select = fake_execute_select

        result = qa.answer_question(
            "Poderia somar o total de vendas do item ean 7896018751002?",
            date(2026, 5, 1),
            date(2026, 5, 31),
            None,
            [],
            ["12345678000199"],
        )

        self.assertEqual(result["route"]["intent"], "produto_especifico")
        self.assertEqual(result["route"]["topic"], "venda_item")
        self.assertIn("Produto Teste", result["answer"])
        self.assertIn("R$ 1.200,00", result["answer"])
        self.assertIn("PA/DP", result["answer"])

    def test_product_specific_margin_followup_uses_previous_item(self):
        def fake_execute_select(sql, params):
            self.assertEqual(params["produto_codigo"], "41741")
            return [
                {
                    "produtos_encontrados": 1,
                    "produto_id": 41741,
                    "id_produto_interno": 41741,
                    "ean_gtin": "7896018751002",
                    "produto": "Produto Teste",
                    "quantidade_vendida": 5,
                    "valor_total_vendido_item": 1000,
                    "cmv_estimado_item": 600,
                    "lucro_bruto_item": 400,
                    "margem_item": 0.4,
                    "quantidade_cupons_com_item": 4,
                    "valor_total_cupons_com_item": 1800,
                }
            ]

        qa.execute_select = fake_execute_select

        result = qa.answer_question(
            "Qual a margem obtida nessas vendas?",
            date(2026, 5, 1),
            date(2026, 5, 31),
            None,
            [{"role": "user", "content": "Poderia somar o valor total vendido do item 41741?"}],
            None,
        )

        self.assertEqual(result["route"]["intent"], "produto_especifico")
        self.assertEqual(result["route"]["topic"], "margem_item")
        self.assertIn("40,00%", result["answer"])
        self.assertIn("margem do item", result["answer"])

    def test_product_specific_followup_ignores_assistant_years_in_history(self):
        def fake_execute_select(sql, params):
            self.assertEqual(params["produto_codigo"], "7896018751002")
            return [
                {
                    "produtos_encontrados": 1,
                    "produto_id": 41741,
                    "id_produto_interno": 41741,
                    "ean_gtin": "7896018751002",
                    "produto": "Produto Teste",
                    "quantidade_vendida": 5,
                    "valor_total_vendido_item": 1000,
                    "cmv_estimado_item": 600,
                    "lucro_bruto_item": 400,
                    "margem_item": 0.4,
                    "quantidade_cupons_com_item": 4,
                    "valor_total_cupons_com_item": 1800,
                }
            ]

        qa.execute_select = fake_execute_select

        result = qa.answer_question(
            "Qual a margem obtida nessas vendas?",
            date(2026, 4, 1),
            date(2026, 7, 20),
            None,
            [
                {"role": "user", "content": "Qual o valor total dos cupons que contem esse item? EAN 7896018751002"},
                {
                    "role": "assistant",
                    "content": "No periodo de 2026-04-01 a 2026-07-20, os cupons que continham o item Produto Teste somaram R$ 1.800,00.",
                },
            ],
            None,
        )

        self.assertEqual(result["route"]["topic"], "margem_item")
        self.assertIn("40,00%", result["answer"])

    def test_product_specific_coupon_followup_uses_coupon_total(self):
        def fake_execute_select(sql, params):
            self.assertIn("vendas_validas_com_item", sql)
            return [
                {
                    "produtos_encontrados": 1,
                    "produto_id": 41741,
                    "id_produto_interno": 41741,
                    "ean_gtin": "7896018751002",
                    "produto": "Produto Teste",
                    "quantidade_vendida": 5,
                    "valor_total_vendido_item": 1000,
                    "cmv_estimado_item": 600,
                    "lucro_bruto_item": 400,
                    "margem_item": 0.4,
                    "quantidade_cupons_com_item": 4,
                    "valor_total_cupons_com_item": 1800,
                }
            ]

        qa.execute_select = fake_execute_select

        result = qa.answer_question(
            "Qual o valor total dos cupons que contem esse item?",
            date(2026, 5, 1),
            date(2026, 5, 31),
            None,
            [{"role": "user", "content": "Poderia somar o valor total vendido do item 41741?"}],
            None,
        )

        self.assertEqual(result["route"]["topic"], "cupons_com_item")
        self.assertIn("R$ 1.800,00", result["answer"])
        self.assertIn("total dos cupons", result["answer"])


if __name__ == "__main__":
    unittest.main()
