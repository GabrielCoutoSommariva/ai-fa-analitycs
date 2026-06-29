-- Testes rapidos para confirmar que a camada analytics responde.

\echo 'Smoke 01. Objetos analytics'
select table_schema, table_name, table_type
from information_schema.tables
where table_schema = 'analytics'
order by table_name;

\echo 'Smoke 02. Catalogo de metricas'
select metric_key, metric_name, source_view, value_field
from analytics.ai_metric_catalog
order by metric_key;

\echo 'Smoke 02b. Templates IA'
select template_key, metric_key, question_pattern
from analytics.ai_query_templates
order by template_key;

\echo 'Smoke 03. Ultimos dias com faturamento'
select *
from analytics.kpi_faturamento_diario
order by data desc
limit 20;

\echo 'Smoke 04. Top lojas por faturamento total'
select
  loja_id,
  max(loja) as loja,
  sum(faturamento_liquido) as faturamento_liquido,
  sum(qtd_cupons) as qtd_cupons
from analytics.kpi_faturamento_loja
group by loja_id
order by faturamento_liquido desc
limit 20;

\echo 'Smoke 05. Produtos com prejuizo estimado'
select data, loja_id, produto_id, produto, qtd_vendida, receita_liquida_item, custo_total_estimado, lucro_bruto_estimado
from analytics.kpi_produtos_prejuizo
limit 20;
