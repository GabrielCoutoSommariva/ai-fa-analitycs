# BI Farmacias Associadas

Base modular para transformar o dump `vendas` em uma camada de BI e em contexto consumivel por IA.

## Ordem Recomendada

1. `sql/00_profile_core.sql`
2. `sql/01_analytics_schema.sql`
3. `sql/01_local_dimensions.sql`
4. `sql/02_kpi_views.sql`
5. `sql/03_semantic_catalog.sql`
6. `sql/05_materialized_kpis.sql`
7. `sql/06_ai_kpis.sql`
8. `sql/08_bronze_sales.sql`
9. `sql/09_bronze_fact_views.sql` somente apos validar cobertura completa da bronze
10. `sql/10_valid_sale_kpis.sql`
11. `sql/11_operational_kpis_bronze.sql` enquanto a operacional precisar evitar FDW na janela recente
12. `sql/12_validate_valid_sale_ticket.sql`
13. `sql/99_smoke_tests.sql`

## Principio

As tabelas originais ficam intactas no schema `vendas`.

O schema `analytics` concentra:

- dimensoes limpas
- fatos analiticos
- KPIs
- materialized views consultivas para IA
- catalogo semantico para IA
- regras pendentes de validacao

O schema `silver` guarda dimensoes locais sincronizadas a partir do ERP para evitar consultas FDW em filtros e joins frequentes. Use `select analytics.refresh_local_dimensions();` para sincronizacao completa e `select analytics.refresh_local_dimensions(false);` para refresh leve de dimensoes pequenas.

O schema `bronze` guarda copias locais transacionais por janela de vendas. Use `select * from analytics.refresh_bronze_sales(45);` ou o script `app/scripts/sync-bi-bronze-sales.sh` para recarregar a janela recente. A sincronizacao deduplica registros por `id` e substitui conflitos locais antes do insert para preservar os indices unicos da bronze.

`sql/09_bronze_fact_views.sql` troca `analytics.fact_venda`, `analytics.fact_venda_item` e `analytics.fact_venda_servico` para ler `bronze.vendas_*`. E uma migracao opt-in: nao execute em producao enquanto a bronze estiver apenas com janela parcial, pois dashboards historicos passariam a enxergar somente o periodo carregado localmente.

`sql/11_operational_kpis_bronze.sql` recria `analytics.mv_kpi_operacional_diario` a partir da bronze local para evitar timeout FDW em `vendas.vendas_item`. Enquanto a bronze estiver parcial, a cobertura operacional fica limitada a janela carregada em `bronze.vendas_*`.

`sql/12_validate_valid_sale_ticket.sql` audita a regra homologada de venda valida (`st_caixa in ('PA', 'DP')`), faturamento liquido e ticket medio usando `bronze.vendas_cab`, evitando dependencia de FDW durante conciliacoes operacionais. Use esta validacao enquanto o FDW do cliente estiver instavel ou com credencial pendente de revisao.

## Indicadores Atuais

- faturamento diario
- faturamento mensal
- ticket medio
- quantidade de cupons
- itens por cupom
- quantidade de itens vendidos
- faturamento por loja
- margem bruta percentual
- lucro bruto total
- lucro por produto
- produtos mais lucrativos
- produtos menos lucrativos
- produtos vendidos com prejuizo
- sazonalidade por dia da semana
- descontos e devolucoes por dia
- descontos e devolucoes por produto/mes

## Indicadores Excluidos Por Enquanto

- faturamento por categoria
- faturamento por fabricante
- lucro por categoria

## Pontos Que Precisam De Validacao De Negocio

- regra homologada de venda valida para KPIs executivos: `st_caixa in ('PA', 'DP')`; `DV` fica fora dos KPIs principais e deve ser analisado como devolucao total
- se `vendas_cab.vlr_liquido` ja desconta devolucao
- se `vendas_item.vlr_venda` e valor total do item ou valor unitario
- qual custo deve prevalecer: `custo_real`, `custo_medio`, `custo_ult`, `produto.custo_ult_entrada` ou compra fiscal
- se servicos em `vendas_serv` entram no faturamento
- se estornos, devolucoes e farmacia popular entram nos KPIs executivos
