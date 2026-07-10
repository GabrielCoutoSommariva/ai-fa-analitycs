# Documento Técnico de Validação de KPIs entre BI e ERP

## 1. Introdução

Este documento descreve as principais regras de cálculo, fontes de dados, queries e indicadores utilizados atualmente no BI de Farmácias Associadas.

O objetivo é permitir uma validação conjunta entre cliente, equipe técnica e responsável pelo ERP, comparando os valores apresentados pelo BI com os valores apresentados pelo ERP. A validação deve confirmar se os cálculos são equivalentes, próximos ou se existem diferenças justificadas por regras de negócio, filtros, datas, custos, cancelamentos, devoluções, arredondamentos ou critérios fiscais.

Este documento não substitui a documentação oficial do ERP. Ele registra como o BI calcula os indicadores hoje, com base nas tabelas, views e materialized views atualmente implementadas.

Quando uma regra ainda não está confirmada ou quando não existe dado confiável no BI, a informação está marcada como **A validar** ou **Regra pendente de validação**.

## 2. Visão Geral da Base de Dados

O BI utiliza uma camada analítica no schema `analytics`, construída a partir do schema operacional `vendas` e, em alguns casos, de tabelas auxiliares do schema `cargas`.

### 2.1 Camada Operacional de Origem

As tabelas abaixo estão no banco de origem e são acessadas pelo BI via `postgres_fdw`.

| Tabela | Função | Principais campos utilizados | Relações principais | Informação extraída |
|---|---|---|---|---|
| `vendas.vendas_cab` | Cabeçalho das vendas/cupons | `id`, `id_associado`, `id_loja`, `id_cliente`, `id_atendente`, `nro_venda`, `ticket`, `data`, `hora`, `tipo_venda`, `origem`, `status`, `st_caixa`, `vlr_liquido`, `vlr_produto`, `vlr_servico`, `vlr_desc_usu`, `vlr_desc_sist`, `vlr_devolucao`, `cpf_nf` | Relaciona com `vendas.vendas_item` por `id = id_venda`; relaciona com loja, cliente e atendente | Faturamento, cupons, datas, devoluções, serviços, descontos de cabeçalho e filtros por loja/período |
| `vendas.vendas_item` | Itens vendidos em cada cupom | `id`, `id_venda`, `id_associado`, `id_loja`, `id_produto`, `id_vendedor`, `ean_gtin`, `nome_produto`, `qtd_venda`, `qtd_devol`, `vlr_unitario`, `vlr_venda`, `vlr_devol`, `vlr_desc_usu`, `vlr_desc_sist`, `custo_real`, `custo_medio`, `custo_ult`, `tributacao`, `icms` | Relaciona com `vendas.vendas_cab` por `id_venda`; relaciona com `vendas.produto` por `id_produto` | Quantidade vendida, receita por item, custo estimado, lucro bruto, margem, produtos com prejuízo, vendedores |
| `vendas.vendas_serv` | Serviços vinculados a vendas | `id`, `id_venda`, `id_associado`, `id_loja`, `id_servico`, `nome_serv`, `quantid`, `vlr_unitario`, `vlr_desc`, `valor`, `custo`, `situacao` | Relaciona com `vendas.vendas_cab` por `id_venda` | Valor de serviços, desconto de serviços, custo de serviços, cupons com serviço |
| `vendas.produto` | Cadastro de produtos | `id`, `id_associado`, `id_produto_interno`, `nome`, `gtin`, `preco_bruto`, `preco_liquido`, `custo_ult_entrada` | Relaciona com `vendas.vendas_item` por `id = id_produto` | Nome de produto, GTIN, custo de última entrada como fallback de custo |
| `vendas.loja` | Cadastro de lojas | `id`, `id_associado`, `id_loja_interno`, `nome`, `cnpj` | Relaciona com vendas por `id = id_loja` | Nome de loja, CNPJ, escopo por loja/CNPJ |
| `vendas.associado` | Cadastro de associados/rede | `id`, `id_associado_interno`, `nome`, `cnpj`, `status`, `data_inc`, `matriz`, `regiao`, `porte`, `software` | Relaciona com lojas e vendas por `id_associado` | Dados cadastrais de associado/rede |
| `vendas.cliente` | Cadastro de clientes | `id`, `id_associado`, `id_cliente_interno`, `nome` | Relaciona com venda por `id = id_cliente` | Identificação de clientes ativos, recorrentes e clientes com maior faturamento |
| `vendas.colaborador` | Cadastro de colaboradores/vendedores | `id`, `id_associado`, `id_colaborador_interno`, `nome` | Relaciona com item por `id = id_vendedor` e venda por atendente quando aplicável | Nome de vendedor/colaborador em análises de performance |
| `vendas.nf_entrada_cab` | Cabeçalho de notas de entrada/compras | `id`, `id_fornecedor`, `numero`, `serie`, `modelo`, `data_doc`, `data_lct`, `stat_pr`, `stat_cont`, `stat_fin`, `mov_fin`, `stat_custo` | Relaciona com `vendas.nf_entrada_item` por `id = id_nfiscal` | Compras, fornecedores e dados de entrada. Uso atual no BI: limitado/AI-only, a validar |
| `vendas.nf_entrada_item` | Itens de notas de entrada/compras | `id`, `id_nfiscal`, `id_associado`, `id_loja`, `id_produto`, `nome_produto`, `ean_gtin`, `quantid`, `qtd_calc`, `vlr_unitario`, `vlr_produto`, `vlr_desconto`, `vlr_total`, `vlr_frete`, `vlr_outros`, `vlr_icms`, `vlr_icms_st`, `vlr_ipi`, `vlr_pis`, `vlr_cofins`, `mov_estoq` | Relaciona com `vendas.nf_entrada_cab` | Custo de compra/compras. Regra final para KPIs executivos: a validar |
| `vendas.produto_estoq` | Estoque de produto | A validar | Relaciona com produto/loja | Estoque atual, giro e ruptura. Atualmente sem uso confiável no dashboard; validado anteriormente como indisponível/sem dados úteis |

### 2.2 Views Analíticas Base

As views abaixo compõem a camada lógica do BI.

| View | Origem | Função |
|---|---|---|
| `analytics.fact_venda` | `vendas.vendas_cab` | Normaliza cabeçalho de venda e cria campos derivados como `vlr_liquido_ajustado`, `is_caixa_pago`, `is_devolucao_parcial`, `is_devolucao_total` |
| `analytics.fact_venda_item` | `vendas.vendas_item` + `vendas.produto` | Normaliza itens e calcula quantidade líquida, receita líquida do item, custo base e lucro bruto estimado |
| `analytics.fact_venda_servico` | `vendas.vendas_serv` | Normaliza serviços vinculados a vendas |
| `analytics.fact_compra_item` | `vendas.nf_entrada_item` + `vendas.nf_entrada_cab` | Normaliza itens de compra/entrada. Uso gerencial final: a validar |
| `analytics.dim_loja` | `silver.dim_loja` | Dimensão local de loja, sincronizada a partir de `vendas.loja`, usada para filtros por CNPJ sem tocar o FDW em consultas do dashboard |
| `analytics.dim_produto` | `silver.dim_produto` | Dimensão local de produto e custos cadastrais |
| `analytics.dim_cliente` | `silver.dim_cliente` | Dimensão local de cliente |
| `analytics.dim_colaborador` | `silver.dim_colaborador` | Dimensão local de vendedor/colaborador |
| `analytics.dim_associado` | `silver.dim_associado` | Dimensão local de associado/rede |

### 2.3 Materialized Views de Performance

O dashboard e a IA leem principalmente materialized views no schema `analytics`.

| Materialized view | Finalidade |
|---|---|
| `analytics.mv_kpi_faturamento_diario` | Faturamento, cupons e devoluções por data/loja |
| `analytics.mv_kpi_faturamento_mensal` | Faturamento mensal por loja |
| `analytics.mv_kpi_cupons` | Quantidade de cupons, vendas distintas e tickets distintos |
| `analytics.mv_kpi_itens_vendidos` | Itens vendidos, cupons com item e itens por cupom |
| `analytics.mv_kpi_faturamento_loja` | Ranking/faturamento por loja |
| `analytics.mv_kpi_lucro_produto` | Receita, custo, lucro e margem por produto/data/loja |
| `analytics.mv_kpi_lucro_produto_total_loja` | Agregado de produto por loja, usado quando o período solicitado cobre o período completo |
| `analytics.mv_kpi_lucro_total_diario` | Lucro, custo e margem por data/loja |
| `analytics.mv_kpi_operacional_diario` | Descontos, CMV percentual, cupons de 1 item e serviços |
| `analytics.mv_ai_resumo_executivo_diario` | Contexto executivo para IA |
| `analytics.mv_ai_vendedor_diario` | Performance de vendedor/colaborador |
| `analytics.mv_ai_vendas_horario` | Vendas por hora/faixa horária |
| `analytics.mv_ai_alertas_operacionais` | Alertas automáticos de queda, margem baixa, ticket baixo, prejuízo e data futura |
| `analytics.mv_ai_cliente_diario` | Clientes por data/loja |
| `analytics.mv_ai_produto_mensal` | Produto mensal, curva ABC/tendências gerenciais |

## 3. Mapeamento de KPIs

### 3.1 Faturamento

**Objetivo:** medir o valor líquido vendido no período selecionado.

**Tabelas/views utilizadas:** `analytics.fact_venda`, `analytics.kpi_faturamento_diario`, `analytics.mv_kpi_faturamento_diario`, `analytics.mv_kpi_faturamento_mensal`.

**Campos utilizados:** `vlr_liquido`, `vlr_devolucao`, `vlr_liquido_ajustado`, `data`, `associado_id`, `loja_id`.

**Filtros aplicados:** período (`data_inicio`, `data_fim`), CNPJ/loja autorizada, escopo de CNPJs do token JWT.

**Regra de cálculo atual:**

```text
vlr_liquido_ajustado = vlr_liquido - vlr_devolucao
faturamento = sum(vlr_liquido_ajustado)
```

**Fórmula matemática:**

```text
Faturamento = Σ(vlr_liquido - vlr_devolucao)
```

**Exemplo prático:** se uma loja teve três vendas com `vlr_liquido` de 100, 80 e 50, e devoluções de 0, 10 e 0, o faturamento será `100 + 70 + 50 = 220`.

**Regra homologada com ERP:** o BI considera apenas vendas com `st_caixa in ('PA', 'DP')` nos indicadores principais. Registros com `st_caixa = 'DV'` representam devolução total e ficam fora dos KPIs executivos, permanecendo disponíveis para análises específicas de devolução.

**Observações importantes:** atualmente o BI usa faturamento líquido ajustado por devolução. A regra de `st_caixa` evita que devoluções totais (`DV`) entrem na quantidade de vendas/cupons, ticket médio, itens e indicadores derivados. Vendas com devolução parcial (`DP`) continuam entrando já abatidas pelo valor de devolução.

**Possíveis diferenças em relação ao ERP:** ERP pode usar valor bruto, valor líquido antes/depois de desconto, data fiscal, data de movimento, status de caixa ou cancelamentos de forma diferente.

**Informação gerencial:** análise de vendas totais, tendência, comparação de lojas e evolução por período.

### 3.2 Quantidade de Cupons

**Objetivo:** medir quantidade de vendas/cupons no período.

**Tabelas/views utilizadas:** `analytics.fact_venda`, `analytics.kpi_cupons`, `analytics.mv_kpi_cupons`, `analytics.mv_kpi_faturamento_diario`.

**Campos utilizados:** `venda_id`, `nro_venda`, `ticket`, `data`, `loja_id`.

**Regra de cálculo atual:** nas views de faturamento, `qtd_cupons = count(*)` sobre vendas válidas em `analytics.fact_venda`, isto é, `st_caixa in ('PA', 'DP')`. A MV de cupons também calcula `count(distinct nro_venda)` e `count(distinct ticket) filter (where ticket is not null)` para auditoria.

**Fórmula matemática:**

```text
Quantidade de cupons = count(linhas de venda em analytics.fact_venda onde st_caixa in ('PA', 'DP'))
```

**Exemplo prático:** se existem 500 linhas em `fact_venda` para a loja no período, o BI apresenta 500 cupons.

**Observações importantes:** a validação deve confirmar se o ERP considera `count(*)`, `nro_venda` distinto, `ticket` distinto ou outro identificador fiscal.

**Possíveis diferenças em relação ao ERP:** cupons cancelados, devolvidos, duplicados, reprocessados, vendas com `ticket` nulo ou diferenças entre `nro_venda` e cupom fiscal.

**Informação gerencial:** fluxo de atendimento, volume de vendas e base para ticket médio.

### 3.3 Ticket Médio

**Objetivo:** medir valor médio por cupom.

**Tabelas/views utilizadas:** `analytics.mv_kpi_faturamento_diario`, `analytics.kpi_ticket_medio`.

**Campos utilizados:** `faturamento_liquido`, `qtd_cupons`.

**Regra de cálculo atual:**

```text
ticket_medio = sum(faturamento_liquido) / sum(qtd_cupons)
```

**Fórmula matemática:**

```text
Ticket médio = Faturamento / Quantidade de cupons
```

**Exemplo prático:** faturamento de R$ 10.000,00 e 200 cupons resulta em ticket médio de R$ 50,00.

**Observações importantes:** se `qtd_cupons = 0`, o BI retorna `0` ou `null`, dependendo do endpoint/view.

**Validação ERP:** regra de ticket médio validada contra o ERP apos aplicação do filtro `st_caixa in ('PA', 'DP')`.

**Resultado de auditoria registrado:** para o período fechado `2026-06-01` a `2026-07-01`, a validação local em `bronze.vendas_cab` apresentou `758737` vendas válidas, faturamento válido de `45778779.01` e ticket médio válido de `60.3355036198313777`. A comparação com `analytics.mv_kpi_faturamento_diario` apresentou diferença residual de `1` cupom e `409.31` em faturamento, tratada como pendência técnica de sincronização/cobertura entre bronze local e MVs/fonte live.

**Informação gerencial:** qualidade de cesta, valor médio de compra, impacto de mix e promoções.

### 3.4 CMV / Custo Total Estimado

**Objetivo:** estimar o custo das mercadorias vendidas para análise de margem.

**Tabelas/views utilizadas:** `analytics.fact_venda_item`, `analytics.mv_kpi_lucro_produto`, `analytics.mv_kpi_lucro_total_diario`, `analytics.mv_kpi_operacional_diario`.

**Campos utilizados:** `qtd_venda`, `qtd_devol`, `custo_real`, `custo_medio`, `custo_ult`, `custo_ult_entrada`, `custo_unitario_base`, `custo_total_base`, `receita_liquida_item`.

**Regra de cálculo atual:**

```text
qtd_liquida = qtd_venda - qtd_devol
custo_unitario_base = coalesce(nullif(custo_real, 0), nullif(custo_medio, 0), nullif(custo_ult, 0), nullif(custo_ult_entrada, 0), 0)
custo_total_estimado = qtd_liquida * custo_unitario_base
cmv_percentual = sum(custo_total_estimado) / sum(receita_liquida_item)
```

**Fórmula matemática:**

```text
CMV = Σ((qtd_venda - qtd_devol) × custo_unitario_base)
CMV % = CMV / Receita líquida dos itens
```

**Exemplo prático:** 10 unidades líquidas com custo unitário de R$ 4,00 geram CMV de R$ 40,00.

**Observações importantes:** este CMV é gerencial/estimado e usa prioridade de custo disponível. Não é necessariamente o CMV contábil do ERP.

**Possíveis diferenças em relação ao ERP:** ERP pode usar custo médio fiscal, custo contábil, custo por lote, custo da entrada, custo com impostos, custo sem impostos ou custo atualizado em outro momento.

**Informação gerencial:** análise de margem, produtos com prejuízo e rentabilidade por loja/produto.

### 3.5 Custo de Compra

**Objetivo:** analisar valores de entrada/compra quando aplicável.

**Tabelas/views utilizadas:** `analytics.fact_compra_item`, originada de `vendas.nf_entrada_item` e `vendas.nf_entrada_cab`.

**Campos utilizados:** `quantid`, `qtd_calc`, `vlr_unitario`, `vlr_produto`, `vlr_desconto`, `vlr_total`, `vlr_frete`, `vlr_outros`, `vlr_icms`, `vlr_icms_st`, `vlr_ipi`, `vlr_pis`, `vlr_cofins`, `mov_estoq`, `data_doc`, `data_lct`, `stat_custo`.

**Regra de cálculo atual:** uso final em cards executivos não está consolidado. **A validar**.

**Fórmula matemática:** **A validar com ERP**.

**Observações importantes:** os dados de compra existem na camada analítica, mas o dashboard executivo atual prioriza custo estimado por item vendido.

**Possíveis diferenças em relação ao ERP:** inclusão/exclusão de impostos, frete, descontos, bonificações, devoluções de compra, data de emissão versus lançamento.

**Informação gerencial:** compras por fornecedor, variação de custo e análise de abastecimento, quando homologado.

### 3.6 Margem Bruta

**Objetivo:** medir lucro bruto estimado das vendas.

**Tabelas/views utilizadas:** `analytics.fact_venda_item`, `analytics.mv_kpi_lucro_produto`, `analytics.mv_kpi_lucro_total_diario`.

**Campos utilizados:** `venda_liquida_item`, `custo_total_base`, `lucro_bruto_estimado`.

**Regra de cálculo atual:**

```text
lucro_bruto_estimado = venda_liquida_item - custo_total_base
```

**Fórmula matemática:**

```text
Margem bruta em valor = Receita líquida dos itens - CMV estimado
```

**Exemplo prático:** receita líquida de R$ 100,00 e CMV estimado de R$ 65,00 resultam em margem bruta de R$ 35,00.

**Observações importantes:** lucro e margem são estimados até homologação definitiva da regra de custo com o ERP.

**Possíveis diferenças em relação ao ERP:** custo utilizado, impostos, descontos, devoluções e arredondamentos.

**Informação gerencial:** rentabilidade por produto, loja, vendedor e período.

### 3.7 Margem Percentual

**Objetivo:** medir percentual de lucro bruto sobre a receita líquida dos itens.

**Tabelas/views utilizadas:** `analytics.mv_kpi_lucro_produto`, `analytics.mv_kpi_lucro_total_diario`.

**Campos utilizados:** `lucro_bruto_estimado`, `lucro_bruto_total`, `receita_liquida_item`.

**Regra de cálculo atual:**

```text
margem_bruta_percentual = sum(lucro_bruto_estimado) / sum(receita_liquida_item)
```

**Fórmula matemática:**

```text
Margem % = Margem bruta / Receita líquida dos itens
```

**Exemplo prático:** margem bruta de R$ 35,00 sobre receita de R$ 100,00 resulta em 35%.

**Observações importantes:** quando a receita é zero, o BI retorna `null`.

**Possíveis diferenças em relação ao ERP:** base de receita, custo, impostos e devoluções.

**Informação gerencial:** avaliação de rentabilidade e saúde comercial.

### 3.8 Vendas por Loja

**Objetivo:** comparar faturamento e cupons entre lojas.

**Tabelas/views utilizadas:** `analytics.mv_kpi_faturamento_loja`, `analytics.dim_loja`.

**Campos utilizados:** `loja_id`, `loja`, `cnpj`, `qtd_cupons`, `faturamento_liquido`, `data`.

**Regra de cálculo atual:** soma do faturamento líquido por `loja_id` no período, com filtro por CNPJ autorizado quando aplicável.

**Fórmula matemática:**

```text
Vendas por loja = Σ(faturamento_liquido) agrupado por loja_id
```

**Exemplo prático:** loja A soma R$ 50.000,00, loja B soma R$ 35.000,00; ranking ordena por maior faturamento.

**Observações importantes:** em produção, `analytics.dim_loja` lê `silver.dim_loja`, sincronizada a partir de `vendas.loja`, para manter filtros e joins frequentes fora do caminho FDW.

**Possíveis diferenças em relação ao ERP:** agrupamento por loja interna, CNPJ, matriz/rede, lojas inativas ou remapeamento cadastral.

**Informação gerencial:** ranking de lojas, lojas fortes/fracas e comparação com rede.

### 3.9 Vendas por Produto

**Objetivo:** medir receita, quantidade, custo e lucro por produto.

**Tabelas/views utilizadas:** `analytics.mv_kpi_lucro_produto`, `analytics.mv_kpi_lucro_produto_total_loja`.

**Campos utilizados:** `produto_id`, `produto`, `qtd_vendida`, `receita_liquida_item`, `custo_total_estimado`, `lucro_bruto_estimado`, `margem_bruta_percentual`.

**Regra de cálculo atual:** agrupamento por `produto_id` com soma de quantidade líquida, receita líquida, custo e lucro.

**Fórmula matemática:**

```text
Qtd vendida = Σ(qtd_venda - qtd_devol)
Receita produto = Σ(vlr_venda - vlr_devol)
Lucro produto = Σ(receita líquida do item - custo total estimado)
```

**Exemplo prático:** produto com 100 unidades líquidas, receita de R$ 2.000,00 e custo estimado de R$ 1.300,00 gera lucro de R$ 700,00.

**Observações importantes:** produtos sem custo recebem custo zero na regra atual após fallback, o que pode inflar margem. Deve ser validado.

**Possíveis diferenças em relação ao ERP:** cadastro de produto, EAN/GTIN, custo usado, devoluções, kits e serviços.

**Informação gerencial:** mix, rentabilidade, produtos líderes e produtos problemáticos.

### 3.10 Vendas por Categoria

**Objetivo:** analisar vendas por categoria/grupo de produto.

**Status atual:** **A validar**. Nas views e serviços analisados não há campo de categoria de produto exposto no dashboard atual.

**Tabela/campo provável:** `vendas.produto` ou tabela auxiliar de categoria. Nome do campo/tabela: **A confirmar**.

**Regra de cálculo:** **Regra pendente de validação**.

**Possíveis diferenças em relação ao ERP:** categoria comercial, categoria fiscal, grupo/subgrupo, classificação interna ou classificação por indústria.

### 3.11 Vendas por Período

**Objetivo:** analisar evolução no tempo.

**Tabelas/views utilizadas:** `analytics.mv_kpi_faturamento_diario`, `analytics.mv_kpi_faturamento_mensal`.

**Campos utilizados:** `data`, `mes`, `faturamento_liquido`, `qtd_cupons`.

**Regra de cálculo atual:** agrupamento por dia, mês ou ano conforme granularidade.

**Regra automática de granularidade:**

```text
até 90 dias: dia
91 a 730 dias: mês
acima de 730 dias: ano
```

**Fórmula matemática:**

```text
Vendas por período = Σ(faturamento_liquido) agrupado por data/mês/ano
```

**Informação gerencial:** tendência de vendas, sazonalidade e evolução histórica.

### 3.12 Comparativo entre Períodos

**Objetivo:** comparar período atual com período anterior equivalente.

**Tabelas/views utilizadas:** `analytics.mv_ai_resumo_executivo_diario`.

**Campos utilizados:** `faturamento_liquido`, `qtd_cupons`, `lucro_bruto_total`, `data`.

**Regra de cálculo atual na IA:** período anterior com a mesma duração imediatamente antes de `data_inicio`.

**Fórmula matemática:**

```text
Variação = (valor_atual - valor_anterior) / valor_anterior
```

**Exemplo prático:** se o faturamento atual é R$ 120.000,00 e o anterior R$ 100.000,00, variação = 20%.

**Observações importantes:** se período anterior tem valor zero, o BI retorna `null` para variação.

### 3.13 Produtos Mais Vendidos

**Objetivo:** identificar produtos com maior volume/receita/lucro.

**Tabelas/views utilizadas:** `analytics.mv_kpi_lucro_produto`, `analytics.mv_ai_produto_mensal`.

**Campos utilizados:** `qtd_vendida`, `receita_liquida_item`, `lucro_bruto_estimado`.

**Regra atual:** no dashboard, rankings de produto priorizam lucro ou prejuízo. Para “mais vendidos” por quantidade, a regra deve ordenar por `sum(qtd_vendida) desc`; uso final no dashboard: **A validar**.

**Possíveis diferenças em relação ao ERP:** ranking por quantidade, valor bruto, valor líquido, lucro ou unidades líquidas.

### 3.14 Produtos com Baixa Venda

**Objetivo:** identificar produtos com pouca saída.

**Status atual:** **A validar**. O BI possui dados de `qtd_vendida`, mas não há KPI executivo formal de baixa venda no dashboard atual.

**Regra sugerida para validação:** produtos com `sum(qtd_vendida)` abaixo de um limite em determinado período.

**Campos:** `produto_id`, `produto`, `qtd_vendida`, `data` ou `mes`.

### 3.15 Curva ABC

**Objetivo:** classificar produtos por representatividade de faturamento/receita.

**Tabelas/views utilizadas:** `analytics.mv_ai_produto_mensal`.

**Campos utilizados:** `produto_id`, `produto`, `receita_liquida_item`.

**Regra atual na IA:** calcula receita total, receita acumulada por produto em ordem decrescente de receita e classifica:

```text
A: até 80% da receita acumulada
B: acima de 80% até 95%
C: acima de 95%
```

**Observações importantes:** curva ABC está em uso consultivo/IA e não como card principal do dashboard.

**Possíveis diferenças em relação ao ERP:** curva por faturamento, margem, quantidade, custo ou período específico.

### 3.16 Estoque Atual

**Status atual:** **A validar / indisponível para dashboard atual**.

Há tabela `vendas.produto_estoq`, mas o estoque não está homologado como KPI do dashboard. Em validações anteriores, a tabela não apresentou dados confiáveis para uso imediato.

**Campos/tabelas:** `vendas.produto_estoq`, campos a confirmar.

**Regra:** pendente de validação com ERP.

### 3.17 Giro de Estoque

**Status atual:** **A validar / não calculado atualmente**.

**Regra usual:**

```text
Giro = CMV ou quantidade vendida / estoque médio
```

**Dependências:** estoque inicial/final ou estoque médio confiável, movimentações de entrada/saída e regra de custo.

### 3.18 Ruptura

**Status atual:** **A validar / não calculado atualmente**.

**Regra necessária:** identificar produto sem estoque com demanda/venda esperada. O BI atual não possui regra homologada.

### 3.19 Descontos

**Objetivo:** medir descontos manuais, automáticos e seu impacto.

**Tabelas/views utilizadas:** `analytics.mv_kpi_operacional_diario`, `analytics.mv_ai_desconto_devolucao_diario`.

**Campos utilizados:** `desconto_manual`, `desconto_automatico`, `desconto_total`, `receita_liquida_item`, `custo_total_estimado`.

**Regra atual:**

```text
desconto_manual = Σ(vlr_desc_usu)
desconto_automatico = Σ(vlr_desc_sist)
desconto_total = desconto_manual + desconto_automatico
% desconto manual = desconto_manual / receita_liquida_item
% desconto automático = desconto_automatico / receita_liquida_item
% desconto / CMV = desconto_total / custo_total_estimado
```

**Possíveis diferenças em relação ao ERP:** desconto no cabeçalho versus item, desconto antes/depois de devolução, desconto financeiro, desconto de serviço e arredondamentos.

### 3.20 Devoluções

**Objetivo:** medir impacto de devoluções.

**Tabelas/views utilizadas:** `analytics.fact_venda`, `analytics.fact_venda_item`, `analytics.mv_kpi_faturamento_diario`, `analytics.mv_ai_vendas_horario`.

**Campos utilizados:** `vlr_devolucao`, `vlr_devol`, `qtd_devol`, `valor_devolucao`.

**Regra atual:** no faturamento, a devolução é subtraída do `vlr_liquido`. Nos itens, receita líquida do item é `vlr_venda - vlr_devol` e quantidade líquida é `qtd_venda - qtd_devol`.

**Possíveis diferenças em relação ao ERP:** devolução parcial, devolução total, cancelamento versus devolução, data original da venda versus data da devolução.

### 3.21 Cupons com 1 Item

**Objetivo:** indicar concentração de cupons pequenos, potencial oportunidade de aumento de cesta.

**Tabelas/views utilizadas:** `analytics.mv_kpi_operacional_diario`.

**Campos utilizados:** `total_cupons`, `cupons_um_item`, `qtd_itens`.

**Regra atual:**

```text
cupons_um_item = count(cupons where sum(qtd_liquida) = 1)
percentual_cupons_um_item = cupons_um_item / total_cupons
```

### 3.22 Vendas por Vendedor

**Objetivo:** analisar performance de vendedores/colaboradores.

**Tabelas/views utilizadas:** `analytics.mv_ai_vendedor_diario`.

**Campos utilizados:** `vendedor_id`, `vendedor`, `qtd_vendas`, `qtd_itens_vendidos`, `valor_vendido`, `ticket_medio`, `custo_total_estimado`, `lucro_bruto_estimado`, `margem_bruta_percentual`, `desconto_manual`, `desconto_automatico`, `valor_devolucao`.

**Regra atual:** agrupamento por vendedor, data e loja. Para perguntas de margem, o BI considera vendedores com pelo menos R$ 100,00 vendidos para evitar distorções de cupons residuais.

### 3.23 Vendas por Horário

**Objetivo:** identificar horários/faixas com maior movimento.

**Tabelas/views utilizadas:** `analytics.mv_ai_vendas_horario`.

**Campos utilizados:** `hora`, `faixa_horaria`, `qtd_cupons`, `faturamento_liquido`, `ticket_medio`, `valor_devolucao`.

**Faixas atuais:**

```text
0-5: madrugada
6-11: manha
12-17: tarde
18-23: noite
```

### 3.24 Sazonalidade por Dia da Semana

**Objetivo:** analisar faturamento por dia da semana.

**Tabelas/views utilizadas:** `analytics.mv_ai_sazonalidade_dia_semana`.

**Campos utilizados:** `dia_semana`, `nome_dia_semana`, `data`, `qtd_cupons`, `faturamento_liquido`, `ticket_medio`.

**Regra:** soma por dia da semana dentro do período e cálculo de ticket médio.

### 3.25 Clientes

**Objetivo:** analisar clientes identificados.

**Tabelas/views utilizadas:** `analytics.mv_ai_cliente_diario`.

**Campos utilizados:** `cliente_id`, `cliente`, `qtd_cupons`, `faturamento_liquido`, `ticket_medio`, `primeira_compra_loja`, `ultima_compra_loja`.

**Regra atual:** clientes ativos são clientes com venda identificada no período. Clientes inativos não são calculados na lista rápida para evitar consulta pesada.

**Observação:** depende de `cliente_id` preenchido na venda.

## 4. Estrutura Lógica das Queries

### 4.1 Query de Resumo Executivo

**Finalidade:** alimentar cards principais do dashboard: faturamento, cupons, ticket médio, itens, lucro bruto e margem.

**Tabelas envolvidas:** `analytics.mv_kpi_faturamento_diario`, `analytics.mv_kpi_itens_vendidos`, `analytics.mv_kpi_lucro_total_diario`.

**Joins utilizados:** `cross join` entre agregados independentes (`fat`, `itens`, `lucro`).

**Agrupamentos:** não há agrupamento final; cada CTE retorna total do filtro.

**Filtros:** período (`data_inicio`, `data_fim`), CNPJ específico ou lista de CNPJs autorizados.

**Campos calculados:** `ticket_medio = faturamento / cupons`, `margem = lucro / receita`.

**Resultado esperado:** uma linha consolidada para o período/escopo.

**Uso:** cards executivos e contexto de IA.

### 4.2 Query de Rede/Matriz

**Finalidade:** comparar os cards do usuário com o total geral da rede.

**Tabelas envolvidas:** mesmas da query de resumo.

**Filtros:** período apenas. Não aplica filtro de CNPJ autorizado.

**Resultado esperado:** uma linha com totais gerais do banco para comparação visual.

**Observação:** no frontend, o texto visual usa “Rede”.

### 4.3 Query de Tendência de Faturamento

**Finalidade:** alimentar gráfico “Faturamento e cupons”.

**Tabela envolvida:** `analytics.mv_kpi_faturamento_diario`.

**Agrupamento:** por dia, mês ou ano.

**Regra de granularidade:** auto conforme tamanho do período.

**Campos calculados:** `sum(qtd_cupons)`, `sum(faturamento_liquido)`.

**Uso:** gráfico temporal e análise de tendência.

### 4.4 Query de Faturamento por Loja

**Finalidade:** ranking de lojas e gráfico de barras.

**Tabelas envolvidas:** `analytics.mv_kpi_faturamento_loja`, `analytics.dim_loja`.

**Joins:** `left join` das vendas agregadas com dimensão de lojas.

**Filtros:** período e CNPJ/autorização.

**Agrupamento:** por `loja_id` na CTE de vendas.

**Resultado esperado:** lista de lojas com `qtd_cupons` e `faturamento_liquido`.

**Observação técnica:** `analytics.dim_loja` deve apontar para `silver.dim_loja` nos ambientes publicados; se apenas o script base for aplicado, ela volta a depender de FDW.

### 4.5 Query de Lucro por Produto

**Finalidade:** produtos mais/menos lucrativos e produtos com prejuízo.

**Tabelas envolvidas:** `analytics.mv_kpi_lucro_produto` ou `analytics.mv_kpi_lucro_produto_total_loja`.

**Regra de escolha da fonte:** se o período cobre todo o período disponível, usa agregação total por loja; caso contrário, usa MV por data.

**Agrupamento:** por `produto_id`.

**Campos calculados:** `sum(qtd_vendida)`, `sum(receita_liquida_item)`, `sum(custo_total_estimado)`, `sum(lucro_bruto_estimado)`, margem.

**Uso:** gráficos e tabelas de produto/margem; IA de produtos.

### 4.6 Query de Produtos com Prejuízo

**Finalidade:** listar produtos com resultado bruto negativo.

**Tabelas envolvidas:** mesmas da query de lucro por produto.

**Condição:**

```text
having sum(lucro_bruto_estimado) < 0
```

**Ordenação:** `lucro_bruto_estimado asc`.

**Uso:** alertas, overview, aba de margem e IA.

### 4.7 Query Operacional

**Finalidade:** alimentar cards operacionais: desconto usuário, desconto automático, desconto/CMV e cupons com 1 item.

**Tabela envolvida:** `analytics.mv_kpi_operacional_diario`.

**Campos calculados:** percentuais de desconto, CMV percentual, cupons com 1 item.

**Uso:** cards operacionais no dashboard.

### 4.8 Query de IA: Vendedores

**Finalidade:** responder perguntas sobre vendedores, venda, margem, descontos e performance.

**Tabela envolvida:** `analytics.mv_ai_vendedor_diario`.

**Agrupamento:** vendedor no período/filtro.

**Campos calculados:** total vendido, ticket médio, itens por venda, lucro, margem, desconto e devolução.

### 4.9 Query de IA: Horários

**Finalidade:** responder melhor horário/faixa de movimento.

**Tabela envolvida:** `analytics.mv_ai_vendas_horario`.

**Agrupamento:** `hora`.

**Resultado:** faturamento, cupons e ticket médio por hora.

### 4.10 Query de IA: Clientes

**Finalidade:** responder clientes ativos e clientes com maior faturamento.

**Tabela envolvida:** `analytics.mv_ai_cliente_diario`.

**Observação:** clientes inativos não são calculados na lista rápida.

### 4.11 Query de Alertas

**Finalidade:** listar alertas operacionais.

**Tabela envolvida:** `analytics.mv_ai_alertas_operacionais`.

**Tipos de alerta atuais:** queda de faturamento, margem baixa/negativa, ticket baixo, produtos com prejuízo, venda com data futura.

## 5. Regras Matemáticas dos Indicadores

| Indicador | Fórmula atual no BI | Observação |
|---|---|---|
| Faturamento | `Σ(vlr_liquido - vlr_devolucao)` | Usa `vlr_liquido_ajustado` |
| Cupons | `count(*)` sobre `fact_venda` | Validar se ERP usa cupom fiscal distinto |
| Ticket médio | `faturamento / qtd_cupons` | Base depende da regra de cupons |
| Quantidade líquida vendida | `qtd_venda - qtd_devol` | Item de venda |
| Receita líquida item | `vlr_venda - vlr_devol` | Item de venda |
| Custo unitário base | `coalesce(custo_real, custo_medio, custo_ult, custo_ult_entrada, 0)`, ignorando zeros | Regra de prioridade a validar |
| CMV estimado | `Σ(qtd_liquida × custo_unitario_base)` | Gerencial, não necessariamente contábil |
| CMV percentual | `Σ(custo_total_estimado) / Σ(receita_liquida_item)` | Retorna `null` se receita zero |
| Lucro bruto estimado | `Σ(receita_liquida_item - custo_total_estimado)` | Base de margem |
| Margem percentual | `lucro_bruto_estimado / receita_liquida_item` | Retorna `null` se receita zero |
| Desconto manual | `Σ(vlr_desc_usu)` | Item de venda na MV operacional |
| Desconto automático | `Σ(vlr_desc_sist)` | Item de venda na MV operacional |
| Desconto total | `desconto_manual + desconto_automatico` | Pode divergir se ERP usa desconto de cabeçalho |
| Percentual desconto/CMV | `desconto_total / custo_total_estimado` | KPI operacional |
| Cupons com 1 item | `count(cupons where Σ(qtd_liquida) = 1)` | Base por venda/cupom |
| Curva ABC | Receita acumulada: A até 80%, B até 95%, C acima | Uso consultivo/IA |
| Variação entre períodos | `(atual - anterior) / anterior` | Período anterior equivalente |

## 6. Validações com o Cliente/ERP

### 6.1 Regras Homologadas

As regras abaixo foram homologadas para os KPIs executivos atuais:

1. Venda válida para KPIs principais: `st_caixa in ('PA', 'DP')`.
2. Devolução total: `st_caixa = 'DV'` fica fora dos KPIs executivos e permanece disponível para análise específica de devoluções.
3. Faturamento líquido: `sum(vlr_liquido - vlr_devolucao)` sobre vendas válidas.
4. Cupons válidos: `count(*)` sobre vendas válidas.
5. Ticket médio: `faturamento_liquido / cupons_validos`.

Script de auditoria reproduzível: `bi/sql/12_validate_valid_sale_ticket.sql`. Ele usa `bronze.vendas_cab` para evitar dependência de FDW durante auditorias operacionais e compara o resultado com `analytics.mv_kpi_faturamento_diario`.

### 6.2 Validações Ainda Necessárias

As perguntas abaixo devem ser respondidas pelo cliente ou responsável pelo ERP para homologação dos números.

1. Existem exceções à regra homologada `PA/DP` para algum relatório fiscal/financeiro específico?
2. Devoluções totais `DV` devem aparecer somente em relatório separado de devoluções ou em algum KPI executivo secundário?
3. Devoluções são abatidas na data da venda original ou na data da devolução nos relatórios oficiais do ERP?
4. O ERP utiliza outro campo além de `vlr_liquido - vlr_devolucao` para algum relatório específico?
5. Descontos entram antes ou depois do cálculo de margem?
6. O desconto usado pelo ERP vem do item, do cabeçalho ou de ambos?
7. O custo considerado é custo real, custo médio, último custo ou custo de última entrada?
8. O custo inclui impostos, frete, ST, IPI, PIS/COFINS ou outras despesas?
9. O CMV é calculado por item vendido, por movimentação contábil ou por fechamento fiscal?
10. Cupons cancelados têm outro `st_caixa` ou status que precisa ser tratado além de `DV`?
11. Cupons devolvidos parcialmente continuam na contagem? Regra atual homologada: sim, quando `st_caixa = 'DP'`.
12. Existe algum relatório do ERP que conte cupom por `nro_venda`, `ticket`, documento fiscal ou outro identificador, em vez de `count(*)` das vendas válidas?
13. Transferências entre lojas impactam estoque ou custo?
14. Bonificações entram no cálculo de custo?
15. Produtos sem custo cadastrado devem aparecer com custo zero, custo médio da loja ou devem ser excluídos?
16. Serviços entram no faturamento total, margem ou apenas em análise operacional?
17. Vendas com data futura devem ser ignoradas sempre?
18. Qual data deve ser usada: emissão, caixa, movimento, lançamento ou competência?
19. O ERP considera filial por `loja_id`, CNPJ ou código interno?
20. Produtos são comparados por `produto_id`, `id_produto_interno`, EAN/GTIN ou descrição?
21. Categorias de produto existem no ERP? Qual tabela/campo deve ser usado?
22. Estoque atual está disponível em qual tabela/campo confiável?
23. Giro e ruptura devem usar estoque médio, estoque final ou outra regra?
24. Como o ERP arredonda valores monetários e percentuais?
25. Existe diferença entre vendas importadas e vendas efetivadas no ERP?

## 7. Diferenças Possíveis entre BI e ERP

As principais causas de divergência esperadas são:

1. Tratamento diferente de cancelamentos, devoluções parciais e devoluções totais.
2. Uso de valor bruto no ERP versus valor líquido ajustado no BI.
3. Uso de `count(*)` no BI versus cupom fiscal distinto no ERP.
4. Atualização de custos em momentos diferentes.
5. Produtos sem custo cadastrado ou com custo zerado.
6. Uso de custo real, médio, último custo ou custo fiscal diferente.
7. Diferença entre data de emissão, data de movimento e data de caixa.
8. Cupons duplicados, reprocessados ou inconsistentes.
9. Regras fiscais específicas do ERP não refletidas no BI.
10. Arredondamentos diferentes por item, cupom ou total.
11. Serviços incluídos ou excluídos do faturamento/margem.
12. Diferença entre desconto de cabeçalho e desconto de item.
13. Sincronização parcial, atrasada ou incompleta entre ERP e base analítica.
14. Dimensões de loja/produto/cliente divergentes entre cadastro e venda histórica.
15. Regras de estoque, transferência, bonificação e perdas ainda não homologadas.

## 8. Pontos Técnicos Observados na Implementação Atual

1. A maioria dos KPIs do dashboard lê materialized views `analytics.mv_*`, o que é adequado para performance.
2. `analytics.dim_loja` e demais dimensões principais foram localizadas em `silver.dim_*`, reduzindo consultas FDW em filtros e joins frequentes.
3. Refresh de materialized views pesadas pode bloquear consultas se executado durante horário comercial. Recomendação: refresh pesado apenas de madrugada e/ou uso de refresh concorrente/swap de tabela.
4. Estoque, giro e ruptura não estão homologados no dashboard atual.
5. Custo e margem são gerenciais/estimados até validação formal da regra de custo com o ERP.
6. Autorização por CNPJ é aplicada no backend com base no token de sessão.
7. Sem CNPJ selecionado, o BI consolida lojas autorizadas do usuário; com CNPJ selecionado, restringe ao CNPJ autorizado.
8. Comparativo “Rede” nos cards executivos usa total geral do banco, não somente CNPJs autorizados.
9. O FDW do cliente apresentou falha recente de autenticação para o usuário remoto `bahdev_gcouto`; enquanto a credencial não for revisada, auditorias operacionais devem preferir bronze/MVs locais.

## 9. Glossário de Campos Calculados

| Campo calculado | Definição |
|---|---|
| `vlr_liquido_ajustado` | `vlr_liquido - vlr_devolucao` |
| `qtd_liquida` | `qtd_venda - qtd_devol` |
| `venda_liquida_item` | `vlr_venda - vlr_devol` |
| `custo_unitario_base` | Primeiro custo válido entre `custo_real`, `custo_medio`, `custo_ult`, `custo_ult_entrada` |
| `custo_total_base` | `qtd_liquida × custo_unitario_base` |
| `lucro_bruto_estimado` | `venda_liquida_item - custo_total_base` |
| `margem_bruta_percentual` | `lucro_bruto_estimado / venda_liquida_item` ou agregado equivalente |
| `cmv_percentual` | `custo_total_estimado / receita_liquida_item` |
| `percentual_cupons_um_item` | `cupons_um_item / total_cupons` |

## 10. Conclusão

Este documento serve como base para validação conjunta entre a equipe técnica do BI, o cliente e o responsável pelo ERP.

Os KPIs de faturamento, cupons e ticket médio estão homologados para a regra `st_caixa in ('PA', 'DP')`. Os KPIs de produto, margem, CMV estimado, loja, período, descontos, vendedores, horários, clientes e alertas estão documentados conforme a implementação atual.

Os indicadores de estoque, giro, ruptura, categorias de produto e custo de compra ainda dependem de confirmação de tabela, campo e regra oficial do ERP.

Após a validação das perguntas da seção 6, recomenda-se registrar uma versão homologada das regras de cálculo, ajustar o BI onde necessário e usar este documento como referência de auditoria para futuras alterações.

## 11. Anexo: Lista de Artefatos Técnicos Consultados

| Arquivo | Finalidade |
|---|---|
| `bi/sql/01_analytics_schema.sql` | Views analíticas base e fatos/dimensões |
| `bi/sql/01_local_dimensions.sql` | Dimensões locais em `silver` para reduzir dependência de FDW em filtros/joins |
| `bi/sql/02_kpi_views.sql` | Views de KPI base |
| `bi/sql/05_materialized_kpis.sql` | Materialized views do dashboard |
| `bi/sql/06_ai_kpis.sql` | Materialized views consultivas usadas pela IA |
| `bi/sql/07_operational_kpis.sql` | KPIs operacionais |
| `bi/sql/08_bronze_sales.sql` | Camada bronze local para vendas, itens e serviços |
| `app/backend/app/services/metrics.py` | Queries dos endpoints do dashboard |
| `app/backend/app/routes/metrics.py` | Endpoints públicos de métricas |
| `app/backend/app/services/question_answering.py` | Queries e regras usadas pela IA |
