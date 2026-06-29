# BI Farmacias Associadas

Base modular para transformar o dump `vendas` em uma camada de BI e em contexto consumivel por IA.

## Ordem Recomendada

1. `sql/00_profile_core.sql`
2. `sql/01_analytics_schema.sql`
3. `sql/02_kpi_views.sql`
4. `sql/03_semantic_catalog.sql`
5. `sql/99_smoke_tests.sql`

## Principio

As tabelas originais ficam intactas no schema `vendas`.

O schema `analytics` concentra:

- dimensoes limpas
- fatos analiticos
- KPIs
- catalogo semantico para IA
- regras pendentes de validacao

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

## Indicadores Excluidos Por Enquanto

- faturamento por categoria
- faturamento por fabricante
- lucro por categoria

## Pontos Que Precisam De Validacao De Negocio

- quais `status` de `vendas.vendas_cab` representam venda valida
- se `vendas_cab.vlr_liquido` ja desconta devolucao
- se `vendas_item.vlr_venda` e valor total do item ou valor unitario
- qual custo deve prevalecer: `custo_real`, `custo_medio`, `custo_ult`, `produto.custo_ult_entrada` ou compra fiscal
- se servicos em `vendas_serv` entram no faturamento
- se estornos, devolucoes e farmacia popular entram nos KPIs executivos
