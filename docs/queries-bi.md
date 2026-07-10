# Catálogo Técnico de Queries do BI

## 1. Objetivo

Este documento lista as principais queries utilizadas atualmente pelo BI para alimentar cards, gráficos, tabelas, filtros e respostas da IA.

O foco é documentar:

- finalidade de cada query;
- endpoint ou uso no sistema;
- tabelas/views/materialized views envolvidas;
- filtros aplicados;
- agrupamentos e ordenações;
- campos calculados;
- resultado esperado;
- observações para validação com o ERP.

As queries abaixo são apresentadas em formato SQL representativo. No sistema, os parâmetros são enviados pelo backend via `psycopg`, usando placeholders como `%(data_inicio)s`, `%(data_fim)s`, `%(cnpj)s`, `%(cnpjs)s` e `%(limit)s`.

## 2. Regras Gerais de Filtro

### 2.0 Venda Válida Para KPIs Executivos

Os KPIs executivos consideram somente vendas com:

```sql
st_caixa in ('PA', 'DP')
```

`PA` representa venda paga/concluída. `DP` representa venda com devolução parcial e continua entrando já abatida pela devolução. `DV` representa devolução total e fica fora dos KPIs principais, mas deve continuar disponível para análises específicas de devoluções.

### 2.1 Filtro de Período

Quando a query trabalha com data diária, o backend monta:

```sql
data >= %(data_inicio)s
data <= %(data_fim)s
```

Quando a query trabalha com mês:

```sql
mes >= %(mes_inicio)s
mes <= %(mes_fim)s
```

### 2.2 Filtro por CNPJ Selecionado

Quando o usuário seleciona um CNPJ específico:

```sql
loja_id in (
  select filtro_loja.loja_id
  from analytics.dim_loja filtro_loja
  where regexp_replace(coalesce(filtro_loja.cnpj, ''), '\D', '', 'g') = %(cnpj)s
)
```

### 2.3 Filtro por CNPJs Autorizados no Token

Quando o usuário não seleciona CNPJ, o BI consolida somente os CNPJs autorizados no JWT:

```sql
loja_id in (
  select filtro_loja.loja_id
  from analytics.dim_loja filtro_loja
  where regexp_replace(coalesce(filtro_loja.cnpj, ''), '\D', '', 'g') = any(%(cnpjs)s)
)
```

### 2.4 Observação Técnica sobre `analytics.dim_loja`

No script base `01_analytics_schema.sql`, `analytics.dim_loja` nasce como view sobre `vendas.loja`:

```sql
select
  id as loja_id,
  id_associado as associado_id,
  id_loja_interno,
  nome,
  cnpj
from vendas.loja;
```

Como `vendas.loja` vem do banco cliente via FDW, queries que filtram por CNPJ podem tocar o banco remoto se apenas o script base for aplicado. O script `01_local_dimensions.sql` cria dimensões locais em `silver`, sincroniza os dados com `analytics.refresh_local_dimensions()` e redefine `analytics.dim_loja` para ler da tabela local, mantendo o contrato atual do backend. O refresh rápido pode usar `analytics.refresh_local_dimensions(false)` para atualizar só dimensões pequenas.

## 3. Queries de Base Analítica

### 3.0 Camada Bronze Local de Vendas

**Finalidade:** manter cópia local das tabelas transacionais principais para reduzir dependência de FDW no próximo passo da arquitetura.

**Tabelas locais:**

- `bronze.vendas_cab` a partir de `vendas.vendas_cab`.
- `bronze.vendas_item` a partir de `vendas.vendas_item`.
- `bronze.vendas_serv` a partir de `vendas.vendas_serv`.

**Função de sincronização:**

```sql
select * from analytics.refresh_bronze_sales(45);
```

**Regra atual:** recarrega por janela móvel de dias. Para cada venda em `vendas.vendas_cab.data` dentro da janela, carrega um conjunto temporário deduplicado por `id`, remove registros locais conflitantes por `id_venda` e por `id`, e reinsere localmente o cabeçalho, itens e serviços deduplicados.

**Motivo da deduplicação:** a origem pode retornar itens com `id` repetido em recortes diferentes; a bronze mantém índices únicos por `id`, então o refresh precisa substituir conflitos antes do insert para evitar falha em `idx_bronze_vendas_item_id`.

**Status:** camada preparada para migração dos fatos `analytics.fact_venda`, `analytics.fact_venda_item` e `analytics.fact_venda_servico` para origem local. Nesta etapa, os fatos ainda não foram trocados para evitar regressão antes da validação de carga.

**Uso em auditoria:** o script `bi/sql/12_validate_valid_sale_ticket.sql` usa `bronze.vendas_cab` como fonte local para validar venda válida, faturamento líquido e ticket médio sem depender do FDW em tempo de auditoria.

### 3.1 `analytics.fact_venda`

**Finalidade:** normalizar cabeçalho de vendas e criar campos derivados usados nos KPIs.

**Origem:** `vendas.vendas_cab`.

```sql
create or replace view analytics.fact_venda as
select
  vc.id as venda_id,
  vc.id_associado as associado_id,
  vc.id_loja as loja_id,
  vc.id_cliente as cliente_id,
  vc.id_atendente as atendente_id,
  vc.nro_venda,
  vc.ticket,
  vc.data,
  vc.hora,
  vc.nro_caixa,
  vc.tipo_venda,
  vc.origem,
  vc.status,
  vc.st_caixa,
  vc.fcia_popular,
  vc.conferido,
  vc.expedida,
  vc.vlr_liquido,
  vc.vlr_produto,
  vc.vlr_servico,
  vc.vlr_desc_usu,
  vc.vlr_desc_sist,
  vc.vlr_acresc,
  vc.vlr_subsidio,
  vc.vlr_frete,
  vc.vlr_devolucao,
  vc.cpf_nf is not null and btrim(vc.cpf_nf) <> '' as tem_cpf_nf,
  vc.vlr_liquido - vc.vlr_devolucao as vlr_liquido_ajustado,
  vc.st_caixa = 'PA' as is_caixa_pago,
  vc.st_caixa = 'DP' as is_devolucao_parcial,
  vc.st_caixa = 'DV' as is_devolucao_total,
  vc.st_caixa in ('PA', 'DP') as is_venda_valida
from vendas.vendas_cab vc;
```

**Campos calculados:**

- `vlr_liquido_ajustado = vlr_liquido - vlr_devolucao`.
- flags de caixa/devolução baseadas em `st_caixa`.
- `is_venda_valida = st_caixa in ('PA', 'DP')`.

**Regra homologada:** os KPIs executivos filtram `is_venda_valida`, portanto consideram `PA` e `DP` e excluem `DV` dos indicadores principais.

### 3.2 `analytics.fact_venda_item`

**Finalidade:** normalizar itens de venda e calcular receita, custo e lucro por item.

**Origem:** `vendas.vendas_item` + `vendas.produto`.

```sql
create or replace view analytics.fact_venda_item as
select
  vi.id as venda_item_id,
  vi.id_venda as venda_id,
  vi.id_associado as associado_id,
  vi.id_loja as loja_id,
  vi.id_produto as produto_id,
  vi.id_vendedor as vendedor_id,
  vi.ean_gtin,
  vi.nome_produto,
  vi.qtd_venda,
  vi.qtd_devol,
  vi.qtd_venda - vi.qtd_devol as qtd_liquida,
  vi.vlr_unitario,
  vi.vlr_venda,
  vi.vlr_devol,
  vi.vlr_venda - vi.vlr_devol as venda_liquida_item,
  vi.vlr_desc_usu,
  vi.vlr_desc_sist,
  vi.vlr_subsidio,
  vi.vlr_reembolso,
  vi.custo_real,
  vi.custo_medio,
  vi.custo_ult,
  p.custo_ult_entrada,
  coalesce(
    nullif(vi.custo_real, 0),
    nullif(vi.custo_medio, 0),
    nullif(vi.custo_ult, 0),
    nullif(p.custo_ult_entrada, 0)
  ) as custo_unitario_base,
  (vi.qtd_venda - vi.qtd_devol) * coalesce(
    nullif(vi.custo_real, 0),
    nullif(vi.custo_medio, 0),
    nullif(vi.custo_ult, 0),
    nullif(p.custo_ult_entrada, 0),
    0
  ) as custo_total_base,
  (vi.vlr_venda - vi.vlr_devol) - ((vi.qtd_venda - vi.qtd_devol) * coalesce(
    nullif(vi.custo_real, 0),
    nullif(vi.custo_medio, 0),
    nullif(vi.custo_ult, 0),
    nullif(p.custo_ult_entrada, 0),
    0
  )) as lucro_bruto_estimado
from vendas.vendas_item vi
left join vendas.produto p on p.id = vi.id_produto;
```

**Campos calculados:**

- `qtd_liquida = qtd_venda - qtd_devol`.
- `venda_liquida_item = vlr_venda - vlr_devol`.
- `custo_unitario_base` com prioridade: `custo_real`, `custo_medio`, `custo_ult`, `custo_ult_entrada`.
- `custo_total_base = qtd_liquida × custo_unitario_base`.
- `lucro_bruto_estimado = venda_liquida_item - custo_total_base`.

**Observação de validação:** a regra de custo é gerencial e deve ser comparada com a regra oficial do ERP.

### 3.3 `analytics.fact_venda_servico`

**Finalidade:** normalizar serviços vinculados a vendas.

**Origem:** `vendas.vendas_serv`.

```sql
create or replace view analytics.fact_venda_servico as
select
  vs.id as venda_servico_id,
  vs.id_venda as venda_id,
  vs.id_associado as associado_id,
  vs.id_loja as loja_id,
  vs.id_servico as servico_id,
  vs.nome_serv,
  vs.quantid,
  vs.vlr_unitario,
  vs.vlr_desc as desconto_servico,
  vs.valor as valor_servico,
  vs.custo as custo_servico,
  vs.situacao
from vendas.vendas_serv vs;
```

**Uso:** KPIs operacionais de serviços, desconto de serviço e custo de serviço.

### 3.4 `analytics.fact_compra_item`

**Finalidade:** consolidar itens de notas de entrada/compras.

**Origem:** `vendas.nf_entrada_item` + `vendas.nf_entrada_cab`.

```sql
create or replace view analytics.fact_compra_item as
select
  ni.id as compra_item_id,
  ni.id_nfiscal as nf_entrada_id,
  ni.id_associado as associado_id,
  ni.id_loja as loja_id,
  ni.id_produto as produto_id,
  nc.id_fornecedor as fornecedor_id,
  nc.numero,
  nc.serie,
  nc.modelo,
  nc.data_doc,
  nc.data_lct,
  nc.stat_pr,
  nc.stat_cont,
  nc.stat_fin,
  nc.mov_fin,
  nc.stat_custo,
  ni.nome_produto,
  ni.ean_gtin,
  ni.quantid,
  ni.qtd_calc,
  ni.vlr_unitario,
  ni.vlr_produto,
  ni.vlr_desconto,
  ni.vlr_total,
  ni.vlr_frete,
  ni.vlr_outros,
  ni.vlr_icms,
  ni.vlr_icms_st,
  ni.vlr_ipi,
  ni.vlr_pis,
  ni.vlr_cofins,
  ni.mov_estoq
from vendas.nf_entrada_item ni
join vendas.nf_entrada_cab nc on nc.id = ni.id_nfiscal;
```

**Uso atual:** disponível para análise futura de compras/custo, mas ainda pendente de regra homologada no dashboard executivo.

## 4. Queries de Materialização de KPIs

### 4.1 Faturamento Diário

**Materialized view:** `analytics.mv_kpi_faturamento_diario`.

**View base:** `analytics.kpi_faturamento_diario`.

```sql
select
  data,
  associado_id,
  loja_id,
  count(*) as qtd_cupons,
  sum(vlr_liquido_ajustado) as faturamento_liquido,
  sum(vlr_produto) as faturamento_produto,
  sum(vlr_servico) as faturamento_servico,
  sum(vlr_devolucao) as valor_devolucao,
  sum(vlr_liquido) as faturamento_bruto_original
from analytics.fact_venda
group by 1, 2, 3;
```

**Índices:** `data`, `(data, loja_id)`, `loja_id`.

**Alimenta:** cards de faturamento/cupons, gráfico de tendência, período disponível, resumo da IA.

### 4.2 Faturamento Mensal

**Materialized view:** `analytics.mv_kpi_faturamento_mensal`.

```sql
select
  date_trunc('month', data)::date as mes,
  associado_id,
  loja_id,
  count(*) as qtd_cupons,
  sum(vlr_liquido_ajustado) as faturamento_liquido,
  sum(vlr_produto) as faturamento_produto,
  sum(vlr_servico) as faturamento_servico,
  sum(vlr_devolucao) as valor_devolucao,
  sum(vlr_liquido) as faturamento_bruto_original
from analytics.fact_venda
group by 1, 2, 3;
```

**Índices:** `mes`, `(mes, loja_id)`, `loja_id`.

**Alimenta:** gráficos/tabelas mensais e tendência de longo prazo.

### 4.3 Cupons

**Materialized view:** `analytics.mv_kpi_cupons`.

```sql
select
  data,
  associado_id,
  loja_id,
  count(*) as qtd_cupons,
  count(distinct nro_venda) as nro_venda_distintos,
  count(distinct ticket) filter (where ticket is not null) as tickets_distintos
from analytics.fact_venda
group by 1, 2, 3;
```

**Alimenta:** drill-down técnico de cupons e auditoria de contagem.

### 4.4 Itens Vendidos

**Materialized view:** `analytics.mv_kpi_itens_vendidos`.

```sql
select
  fv.data,
  fvi.associado_id,
  fvi.loja_id,
  count(*) as linhas_item,
  count(distinct fvi.venda_id) as cupons_com_item,
  sum(fvi.qtd_liquida) as qtd_itens_vendidos,
  case
    when count(distinct fvi.venda_id) = 0 then 0
    else sum(fvi.qtd_liquida) / count(distinct fvi.venda_id)
  end as itens_por_cupom
from analytics.fact_venda_item fvi
join analytics.fact_venda fv on fv.venda_id = fvi.venda_id
group by 1, 2, 3;
```

**Alimenta:** card de itens vendidos e tabelas técnicas.

### 4.5 Faturamento por Loja

**Materialized view:** `analytics.mv_kpi_faturamento_loja`.

```sql
select
  k.data,
  k.associado_id,
  k.loja_id,
  l.nome as loja,
  k.qtd_cupons,
  k.faturamento_liquido,
  k.faturamento_produto,
  k.faturamento_servico,
  k.valor_devolucao,
  k.faturamento_bruto_original
from analytics.kpi_faturamento_diario k
left join analytics.dim_loja l on l.loja_id = k.loja_id;
```

**Alimenta:** gráfico/ranking de lojas e lista de lojas na IA.

### 4.6 Lucro por Produto

**Materialized view:** `analytics.mv_kpi_lucro_produto`.

```sql
select
  fv.data,
  fvi.associado_id,
  fvi.loja_id,
  fvi.produto_id,
  coalesce(p.nome, fvi.nome_produto) as produto,
  sum(fvi.qtd_liquida) as qtd_vendida,
  sum(fvi.venda_liquida_item) as receita_liquida_item,
  sum(fvi.custo_total_base) as custo_total_estimado,
  sum(fvi.lucro_bruto_estimado) as lucro_bruto_estimado,
  case
    when sum(fvi.venda_liquida_item) = 0 then null
    else sum(fvi.lucro_bruto_estimado) / sum(fvi.venda_liquida_item)
  end as margem_bruta_percentual
from analytics.fact_venda_item fvi
join analytics.fact_venda fv on fv.venda_id = fvi.venda_id
left join analytics.dim_produto p on p.produto_id = fvi.produto_id
group by 1, 2, 3, 4, 5;
```

**Alimenta:** produtos lucrativos, produtos com prejuízo, margem e IA de produtos.

### 4.7 Lucro Total Diário

**Materialized view:** `analytics.mv_kpi_lucro_total_diario`.

```sql
select
  data,
  associado_id,
  loja_id,
  sum(receita_liquida_item) as receita_liquida_item,
  sum(custo_total_estimado) as custo_total_estimado,
  sum(lucro_bruto_estimado) as lucro_bruto_total,
  case
    when sum(receita_liquida_item) = 0 then null
    else sum(lucro_bruto_estimado) / sum(receita_liquida_item)
  end as margem_bruta_percentual
from analytics.mv_kpi_lucro_produto
group by 1, 2, 3;
```

**Alimenta:** cards de lucro bruto, margem e CMV.

### 4.8 KPI Operacional Diário

**Materialized view:** `analytics.mv_kpi_operacional_diario`.

**Finalidade:** materializar desconto manual, desconto automático, CMV percentual, cupons com 1 item e serviços.

```sql
with itens_por_cupom as (
  select
    fv.data,
    fv.associado_id,
    fv.loja_id,
    fv.venda_id,
    coalesce(sum(fvi.qtd_liquida), 0) as qtd_itens
  from analytics.fact_venda fv
  left join analytics.fact_venda_item fvi on fvi.venda_id = fv.venda_id
  where fv.data <= current_date
  group by 1, 2, 3, 4
), itens_diario as (
  select
    fv.data,
    fvi.associado_id,
    fvi.loja_id,
    sum(coalesce(fvi.vlr_desc_usu, 0)) as desconto_manual,
    sum(coalesce(fvi.vlr_desc_sist, 0)) as desconto_automatico,
    sum(coalesce(fvi.vlr_desc_usu, 0) + coalesce(fvi.vlr_desc_sist, 0)) as desconto_total,
    sum(coalesce(fvi.venda_liquida_item, 0)) as receita_liquida_item,
    sum(coalesce(fvi.custo_total_base, 0)) as custo_total_estimado
  from analytics.fact_venda_item fvi
  join analytics.fact_venda fv on fv.venda_id = fvi.venda_id
  where fv.data <= current_date
  group by 1, 2, 3
), cupons_diario as (
  select
    data,
    associado_id,
    loja_id,
    count(*) as total_cupons,
    count(*) filter (where qtd_itens = 1) as cupons_um_item
  from itens_por_cupom
  group by 1, 2, 3
), servicos_diario as (
  select
    fv.data,
    fvs.associado_id,
    fvs.loja_id,
    count(*) as linhas_servico,
    count(distinct fvs.venda_id) as cupons_com_servico,
    sum(coalesce(fvs.valor_servico, 0)) as valor_servico,
    sum(coalesce(fvs.desconto_servico, 0)) as desconto_servico,
    sum(coalesce(fvs.custo_servico, 0)) as custo_servico
  from analytics.fact_venda_servico fvs
  join analytics.fact_venda fv on fv.venda_id = fvs.venda_id
  where fv.data <= current_date
  group by 1, 2, 3
)
select
  c.data,
  c.associado_id,
  c.loja_id,
  c.total_cupons,
  c.cupons_um_item,
  case when c.total_cupons = 0 then null else c.cupons_um_item::numeric / c.total_cupons end as percentual_cupons_um_item,
  coalesce(i.desconto_manual, 0) as desconto_manual,
  coalesce(i.desconto_automatico, 0) as desconto_automatico,
  coalesce(i.desconto_total, 0) as desconto_total,
  coalesce(i.receita_liquida_item, 0) as receita_liquida_item,
  coalesce(i.custo_total_estimado, 0) as custo_total_estimado,
  case when i.receita_liquida_item = 0 then null else i.desconto_manual / i.receita_liquida_item end as percentual_desconto_manual,
  case when i.receita_liquida_item = 0 then null else i.desconto_automatico / i.receita_liquida_item end as percentual_desconto_automatico,
  case when i.receita_liquida_item = 0 then null else i.desconto_total / i.receita_liquida_item end as percentual_desconto_total,
  case when i.custo_total_estimado = 0 then null else i.desconto_total / i.custo_total_estimado end as percentual_desconto_cmv,
  case when i.receita_liquida_item = 0 then null else i.custo_total_estimado / i.receita_liquida_item end as cmv_percentual,
  coalesce(s.linhas_servico, 0) as linhas_servico,
  coalesce(s.cupons_com_servico, 0) as cupons_com_servico,
  coalesce(s.valor_servico, 0) as valor_servico,
  coalesce(s.desconto_servico, 0) as desconto_servico,
  coalesce(s.custo_servico, 0) as custo_servico
from cupons_diario c
left join itens_diario i on i.data = c.data and i.associado_id = c.associado_id and i.loja_id = c.loja_id
left join servicos_diario s on s.data = c.data and s.associado_id = c.associado_id and s.loja_id = c.loja_id;
```

**Alimenta:** cards operacionais do topo.

## 5. Queries dos Endpoints do Dashboard

### 5.1 `/metrics/periodo-vendas`

**Finalidade:** obter primeira e última data de venda disponível.

```sql
select min(data) as data_inicio, max(data) as data_fim
from analytics.mv_kpi_faturamento_diario
where data <= current_date;
```

**Com escopo por CNPJ autorizado:** aplica filtro de `loja_id` por `analytics.dim_loja`.

**Uso:** inicialização dos filtros de data.

### 5.2 `/metrics/lojas-cnpj`

**Finalidade:** listar CNPJs e lojas vinculadas para filtro.

```sql
select
  cnpj,
  regexp_replace(coalesce(cnpj, ''), '\D', '', 'g') as cnpj_digits,
  count(*) as lojas,
  array_agg(json_build_object('loja_id', loja_id, 'loja', nome) order by nome) as lojas_vinculadas
from analytics.dim_loja
where cnpj is not null
  and btrim(cnpj) <> ''
group by cnpj
order by cnpj;
```

**Com usuário autenticado:** aplica filtro por CNPJs autorizados.

**Uso:** dropdown de CNPJ/lojas.

### 5.3 `/metrics/summary`

**Finalidade:** cards executivos do usuário.

```sql
with fat as (
  select
    coalesce(sum(faturamento_liquido), 0) as faturamento,
    coalesce(sum(qtd_cupons), 0) as cupons
  from analytics.mv_kpi_faturamento_diario
  {where}
), itens as (
  select coalesce(sum(qtd_itens_vendidos), 0) as itens
  from analytics.mv_kpi_itens_vendidos
  {where}
), lucro as (
  select
    coalesce(sum(receita_liquida_item), 0) as receita,
    coalesce(sum(custo_total_estimado), 0) as custo,
    coalesce(sum(lucro_bruto_total), 0) as lucro,
    case when sum(receita_liquida_item) = 0 then null else sum(lucro_bruto_total) / sum(receita_liquida_item) end as margem
  from analytics.mv_kpi_lucro_total_diario
  {where}
)
select
  fat.faturamento,
  fat.cupons,
  case when fat.cupons = 0 then 0 else fat.faturamento / fat.cupons end as ticket_medio,
  itens.itens,
  lucro.receita,
  lucro.custo,
  lucro.lucro,
  lucro.margem
from fat cross join itens cross join lucro;
```

**Uso:** cards `Faturamento`, `Cupons`, `Ticket médio`, `Itens vendidos`, `Lucro bruto`, `Margem`.

### 5.4 `/metrics/summary-matriz`

**Finalidade:** total geral da rede para comparação nos cards.

**Query:** mesma estrutura de `/metrics/summary`, mas sem filtro de CNPJ autorizado.

**Uso:** baseline visual “Rede”.

### 5.5 `/metrics/operacional-summary`

**Finalidade:** cards operacionais.

```sql
select
  coalesce(sum(total_cupons), 0) as total_cupons,
  coalesce(sum(cupons_um_item), 0) as cupons_um_item,
  case when sum(total_cupons) = 0 then null else sum(cupons_um_item)::numeric / sum(total_cupons) end as percentual_cupons_um_item,
  coalesce(sum(desconto_manual), 0) as desconto_manual,
  coalesce(sum(desconto_automatico), 0) as desconto_automatico,
  coalesce(sum(desconto_total), 0) as desconto_total,
  coalesce(sum(receita_liquida_item), 0) as receita_liquida_item,
  coalesce(sum(custo_total_estimado), 0) as custo_total_estimado,
  case when sum(receita_liquida_item) = 0 then null else sum(desconto_manual) / sum(receita_liquida_item) end as percentual_desconto_manual,
  case when sum(receita_liquida_item) = 0 then null else sum(desconto_automatico) / sum(receita_liquida_item) end as percentual_desconto_automatico,
  case when sum(receita_liquida_item) = 0 then null else sum(desconto_total) / sum(receita_liquida_item) end as percentual_desconto_total,
  case when sum(custo_total_estimado) = 0 then null else sum(desconto_total) / sum(custo_total_estimado) end as percentual_desconto_cmv,
  case when sum(receita_liquida_item) = 0 then null else sum(custo_total_estimado) / sum(receita_liquida_item) end as cmv_percentual,
  coalesce(sum(linhas_servico), 0) as linhas_servico,
  coalesce(sum(cupons_com_servico), 0) as cupons_com_servico,
  coalesce(sum(valor_servico), 0) as valor_servico,
  coalesce(sum(desconto_servico), 0) as desconto_servico,
  coalesce(sum(custo_servico), 0) as custo_servico
from analytics.mv_kpi_operacional_diario
{where};
```

**Uso:** `Desconto usuário`, `Desconto automático`, `Desconto / CMV`, `Cupons 1 item`.

### 5.6 `/metrics/faturamento-tendencia`

**Finalidade:** gráfico de faturamento e cupons por período.

**Granularidade:** `dia`, `mes`, `ano` ou `auto`.

```sql
select
  {period_expr} as periodo,
  {label_expr} as label,
  %(granularidade)s as granularidade,
  coalesce(sum(qtd_cupons), 0) as qtd_cupons,
  coalesce(sum(faturamento_liquido), 0) as faturamento_liquido
from analytics.mv_kpi_faturamento_diario
{where}
group by 1, 2
order by 1;
```

**Expressões por granularidade:**

| Granularidade | `period_expr` | `label_expr` |
|---|---|---|
| `dia` | `data` | `to_char(data, 'YYYY-MM-DD')` |
| `mes` | `date_trunc('month', data)::date` | `to_char(date_trunc('month', data), 'YYYY-MM')` |
| `ano` | `date_trunc('year', data)::date` | `to_char(date_trunc('year', data), 'YYYY')` |

### 5.7 `/metrics/faturamento-diario`

**Finalidade:** tabela técnica diária.

```sql
select
  data,
  associado_id,
  loja_id,
  qtd_cupons,
  faturamento_liquido,
  faturamento_produto,
  faturamento_servico,
  valor_devolucao
from analytics.mv_kpi_faturamento_diario
{where}
order by data desc, faturamento_liquido desc
limit %(limit)s;
```

### 5.8 `/metrics/faturamento-mensal`

**Finalidade:** tabela técnica mensal.

```sql
select
  mes,
  associado_id,
  loja_id,
  qtd_cupons,
  faturamento_liquido,
  faturamento_produto,
  faturamento_servico,
  valor_devolucao
from analytics.mv_kpi_faturamento_mensal
{where}
order by mes desc, faturamento_liquido desc
limit %(limit)s;
```

### 5.9 `/metrics/faturamento-loja`

**Finalidade:** ranking/lista de lojas.

```sql
with vendas as (
  select
    loja_id,
    max(loja) as loja,
    sum(qtd_cupons) as qtd_cupons,
    sum(faturamento_liquido) as faturamento_liquido
  from analytics.mv_kpi_faturamento_loja
  {vendas_where}
  group by loja_id
)
select
  l.loja_id,
  coalesce(v.loja, l.nome) as loja,
  l.cnpj,
  coalesce(v.qtd_cupons, 0) as qtd_cupons,
  coalesce(v.faturamento_liquido, 0) as faturamento_liquido
from analytics.dim_loja l
left join vendas v on v.loja_id = l.loja_id
{lojas_where}
order by faturamento_liquido desc
limit %(limit)s;
```

**Observação:** inclui lojas autorizadas mesmo que sem faturamento no período, retornando zero.

### 5.10 `/metrics/cupons`

**Finalidade:** tabela técnica de cupons.

```sql
select
  data,
  associado_id,
  loja_id,
  qtd_cupons,
  nro_venda_distintos,
  tickets_distintos
from analytics.mv_kpi_cupons
{where}
order by data desc, qtd_cupons desc
limit %(limit)s;
```

### 5.11 `/metrics/itens-vendidos`

**Finalidade:** tabela técnica de itens vendidos.

```sql
select
  data,
  associado_id,
  loja_id,
  linhas_item,
  cupons_com_item,
  qtd_itens_vendidos,
  itens_por_cupom
from analytics.mv_kpi_itens_vendidos
{where}
order by data desc, qtd_itens_vendidos desc
limit %(limit)s;
```

### 5.12 `/metrics/lucro-produto`

**Finalidade:** produtos mais lucrativos ou menos lucrativos.

```sql
select
  produto_id,
  max(produto) as produto,
  sum(qtd_vendida) as qtd_vendida,
  sum(receita_liquida_item) as receita_liquida_item,
  sum(custo_total_estimado) as custo_total_estimado,
  sum(lucro_bruto_estimado) as lucro_bruto_estimado,
  case when sum(receita_liquida_item) = 0 then null else sum(lucro_bruto_estimado) / sum(receita_liquida_item) end as margem_bruta_percentual
from {source}
{where}
group by produto_id
order by lucro_bruto_estimado {direction}
limit %(limit)s;
```

**Fonte dinâmica:**

- `analytics.mv_kpi_lucro_produto_total_loja` quando o período solicitado cobre todo o período disponível.
- `analytics.mv_kpi_lucro_produto` para períodos filtrados.

### 5.13 `/metrics/produtos-prejuizo`

**Finalidade:** listar produtos com lucro bruto negativo.

```sql
select
  produto_id,
  max(produto) as produto,
  sum(qtd_vendida) as qtd_vendida,
  sum(receita_liquida_item) as receita_liquida_item,
  sum(custo_total_estimado) as custo_total_estimado,
  sum(lucro_bruto_estimado) as lucro_bruto_estimado
from {source}
{where}
group by produto_id
having sum(lucro_bruto_estimado) < 0
order by lucro_bruto_estimado asc
limit %(limit)s;
```

### 5.14 `/metrics/descontos-devolucoes`

**Finalidade:** lista/diagnóstico de descontos e devoluções por dia.

```sql
select
  data,
  associado_id,
  loja_id,
  qtd_cupons,
  faturamento_liquido,
  desconto_manual,
  desconto_automatico,
  desconto_total,
  percentual_desconto,
  valor_devolucao,
  percentual_devolucao
from analytics.mv_ai_desconto_devolucao_diario
{where}
order by data desc, desconto_total desc, valor_devolucao desc
limit %(limit)s;
```

**Observação:** esta MV é versionada em `bi/sql/06_ai_kpis.sql` e atualizada no refresh pesado `app/scripts/refresh-bi-kpis.sh`.

### 5.15 `/metrics/produtos-descontos-devolucoes`

**Finalidade:** produtos com maior desconto ou devolução.

```sql
select
  produto_id,
  max(produto) as produto,
  sum(qtd_liquida) as qtd_liquida,
  sum(receita_liquida_item) as receita_liquida_item,
  sum(desconto_manual) as desconto_manual,
  sum(desconto_automatico) as desconto_automatico,
  sum(desconto_total) as desconto_total,
  sum(valor_devolucao) as valor_devolucao,
  sum(qtd_devolvida) as qtd_devolvida
from analytics.mv_ai_desconto_devolucao_produto_mensal
{where}
group by produto_id
order by {order_column} desc
limit %(limit)s;
```

**Ordenação:** `desconto_total` ou `valor_devolucao`.

### 5.16 `/metrics/sazonalidade-dia-semana`

**Finalidade:** faturamento por dia da semana.

```sql
select
  dia_semana,
  max(nome_dia_semana) as nome_dia_semana,
  count(distinct data) as dias_analisados,
  sum(qtd_cupons) as qtd_cupons,
  sum(faturamento_liquido) as faturamento_liquido,
  case when sum(qtd_cupons) = 0 then 0 else sum(faturamento_liquido) / sum(qtd_cupons) end as ticket_medio
from analytics.mv_ai_sazonalidade_dia_semana
{where}
group by dia_semana
order by faturamento_liquido desc;
```

### 5.17 `/metrics/vendas-horario`

**Finalidade:** faturamento por hora/faixa horária.

```sql
select
  hora,
  max(faixa_horaria) as faixa_horaria,
  count(distinct data) as dias_analisados,
  sum(qtd_cupons) as qtd_cupons,
  sum(faturamento_liquido) as faturamento_liquido,
  case when sum(qtd_cupons) = 0 then 0 else sum(faturamento_liquido) / sum(qtd_cupons) end as ticket_medio,
  sum(valor_devolucao) as valor_devolucao
from analytics.mv_ai_vendas_horario
{where}
group by hora
order by faturamento_liquido desc
limit %(limit)s;
```

## 6. Queries de Materialized Views da IA

### 6.1 Resumo Executivo Diário da IA

**Materialized view:** `analytics.mv_ai_resumo_executivo_diario`.

```sql
select
  f.data,
  f.associado_id,
  f.loja_id,
  regexp_replace(coalesce(l.cnpj, ''), '\D', '', 'g') as cnpj,
  f.qtd_cupons,
  f.faturamento_liquido,
  case when f.qtd_cupons = 0 then 0 else f.faturamento_liquido / f.qtd_cupons end as ticket_medio,
  coalesce(i.qtd_itens_vendidos, 0) as qtd_itens_vendidos,
  coalesce(i.itens_por_cupom, 0) as itens_por_cupom,
  coalesce(g.receita_liquida_item, 0) as receita_liquida_item,
  coalesce(g.custo_total_estimado, 0) as custo_total_estimado,
  coalesce(g.lucro_bruto_total, 0) as lucro_bruto_total,
  g.margem_bruta_percentual,
  f.valor_devolucao
from analytics.mv_kpi_faturamento_diario f
left join analytics.mv_kpi_itens_vendidos i on i.data = f.data and i.associado_id = f.associado_id and i.loja_id = f.loja_id
left join analytics.mv_kpi_lucro_total_diario g on g.data = f.data and g.associado_id = f.associado_id and g.loja_id = f.loja_id
left join analytics.dim_loja l on l.loja_id = f.loja_id
where f.data <= current_date;
```

**Uso:** contexto da IA e comparativos.

### 6.2 Performance de Vendedor

**Materialized view:** `analytics.mv_ai_vendedor_diario`.

```sql
select
  fv.data,
  fvi.associado_id,
  fvi.loja_id,
  regexp_replace(coalesce(l.cnpj, ''), '\D', '', 'g') as cnpj,
  fvi.vendedor_id,
  coalesce(c.nome, 'Sem vendedor') as vendedor,
  count(distinct fvi.venda_id) as qtd_vendas,
  sum(fvi.qtd_liquida) as qtd_itens_vendidos,
  case when count(distinct fvi.venda_id) = 0 then 0 else sum(fvi.qtd_liquida) / count(distinct fvi.venda_id) end as itens_por_venda,
  count(distinct fvi.produto_id) as qtd_skus,
  sum(fvi.venda_liquida_item) as valor_vendido,
  case when count(distinct fvi.venda_id) = 0 then 0 else sum(fvi.venda_liquida_item) / count(distinct fvi.venda_id) end as ticket_medio,
  sum(fvi.custo_total_base) as custo_total_estimado,
  sum(fvi.lucro_bruto_estimado) as lucro_bruto_estimado,
  case when sum(fvi.venda_liquida_item) = 0 then null else sum(fvi.lucro_bruto_estimado) / sum(fvi.venda_liquida_item) end as margem_bruta_percentual,
  sum(coalesce(fvi.vlr_desc_usu, 0)) as desconto_manual,
  sum(coalesce(fvi.vlr_desc_sist, 0)) as desconto_automatico,
  sum(coalesce(fvi.vlr_devol, 0)) as valor_devolucao
from analytics.fact_venda_item fvi
join analytics.fact_venda fv on fv.venda_id = fvi.venda_id
left join analytics.dim_colaborador c on c.colaborador_id = fvi.vendedor_id
left join analytics.dim_loja l on l.loja_id = fvi.loja_id
where fv.data <= current_date
group by 1, 2, 3, 4, 5, 6;
```

**Uso:** perguntas da IA sobre vendedores, margem e performance.

### 6.3 Vendas por Horário

**Materialized view:** `analytics.mv_ai_vendas_horario`.

```sql
select
  fv.data,
  fv.associado_id,
  fv.loja_id,
  regexp_replace(coalesce(l.cnpj, ''), '\D', '', 'g') as cnpj,
  extract(isodow from fv.data)::int as dia_semana,
  extract(hour from fv.hora)::int as hora,
  case
    when extract(hour from fv.hora)::int between 0 and 5 then 'madrugada'
    when extract(hour from fv.hora)::int between 6 and 11 then 'manha'
    when extract(hour from fv.hora)::int between 12 and 17 then 'tarde'
    else 'noite'
  end as faixa_horaria,
  count(*) as qtd_cupons,
  sum(fv.vlr_liquido_ajustado) as faturamento_liquido,
  case when count(*) = 0 then 0 else sum(fv.vlr_liquido_ajustado) / count(*) end as ticket_medio,
  sum(fv.vlr_devolucao) as valor_devolucao
from analytics.fact_venda fv
left join analytics.dim_loja l on l.loja_id = fv.loja_id
where fv.data <= current_date and fv.hora is not null
group by 1, 2, 3, 4, 5, 6, 7;
```

### 6.4 Alertas Operacionais

**Materialized view:** `analytics.mv_ai_alertas_operacionais`.

**Finalidade:** gerar alertas consultivos.

**Regras atuais:**

```sql
-- Queda de faturamento
where faturamento_dia_anterior > 0
  and faturamento_liquido < faturamento_dia_anterior * 0.7

-- Margem baixa ou negativa
where margem_bruta_percentual is not null
  and margem_bruta_percentual < 0.10

-- Ticket médio baixo
where ticket_medio_30d > 0
  and ticket_medio < ticket_medio_30d * 0.8

-- Produtos com prejuízo
where p.lucro_bruto_estimado < 0

-- Data futura
where fv.data > current_date
```

**Uso:** IA e alertas operacionais.

### 6.5 Clientes

**Materialized view:** `analytics.mv_ai_cliente_diario`.

```sql
select
  fv.data,
  fv.associado_id,
  fv.loja_id,
  regexp_replace(coalesce(l.cnpj, ''), '\D', '', 'g') as cnpj,
  fv.cliente_id,
  coalesce(c.nome, 'Cliente sem nome') as cliente,
  count(*) as qtd_cupons,
  sum(fv.vlr_liquido_ajustado) as faturamento_liquido,
  case when count(*) = 0 then 0 else sum(fv.vlr_liquido_ajustado) / count(*) end as ticket_medio,
  sum(fv.vlr_devolucao) as valor_devolucao,
  min(fv.data) over (partition by fv.cliente_id, fv.loja_id) as primeira_compra_loja,
  max(fv.data) over (partition by fv.cliente_id, fv.loja_id) as ultima_compra_loja
from analytics.fact_venda fv
left join analytics.dim_cliente c on c.cliente_id = fv.cliente_id
left join analytics.dim_loja l on l.loja_id = fv.loja_id
where fv.data <= current_date
  and fv.cliente_id is not null
group by 1, 2, 3, 4, 5, 6;
```

**Uso:** clientes ativos e ranking de clientes por faturamento na IA.

### 6.6 Produto Mensal / Curva ABC

**Materialized view:** `analytics.mv_ai_produto_mensal`.

```sql
select
  date_trunc('month', p.data)::date as mes,
  p.associado_id,
  p.loja_id,
  regexp_replace(coalesce(l.cnpj, ''), '\D', '', 'g') as cnpj,
  p.produto_id,
  max(p.produto) as produto,
  sum(p.qtd_vendida) as qtd_vendida,
  sum(p.receita_liquida_item) as receita_liquida_item,
  sum(p.custo_total_estimado) as custo_total_estimado,
  sum(p.lucro_bruto_estimado) as lucro_bruto_estimado,
  case when sum(p.receita_liquida_item) = 0 then null else sum(p.lucro_bruto_estimado) / sum(p.receita_liquida_item) end as margem_bruta_percentual,
  count(distinct p.data) as dias_com_venda
from analytics.mv_kpi_lucro_produto p
left join analytics.dim_loja l on l.loja_id = p.loja_id
where p.data <= current_date
group by 1, 2, 3, 4, 5;
```

**Uso:** perguntas de produtos estratégicos e curva ABC.

### 6.7 Sazonalidade por Dia da Semana

**Materialized view:** `analytics.mv_ai_sazonalidade_dia_semana`.

**Origem:** `analytics.mv_kpi_faturamento_diario` + `analytics.dim_loja`.

**Campos:** `data`, `associado_id`, `loja_id`, `cnpj`, `dia_semana`, `nome_dia_semana`, `qtd_cupons`, `faturamento_liquido`, `ticket_medio`, `valor_devolucao`.

**Uso:** perguntas e endpoint sobre melhor/pior dia da semana.

### 6.8 Descontos e Devoluções Diárias

**Materialized view:** `analytics.mv_ai_desconto_devolucao_diario`.

**Origem:** `analytics.mv_kpi_operacional_diario`, `analytics.mv_kpi_faturamento_diario` e `analytics.dim_loja`.

**Campos:** `data`, `associado_id`, `loja_id`, `cnpj`, `qtd_cupons`, `faturamento_liquido`, `desconto_manual`, `desconto_automatico`, `desconto_total`, `percentual_desconto`, `valor_devolucao`, `percentual_devolucao`.

**Uso:** perguntas e endpoints sobre descontos e devoluções no período.

### 6.9 Descontos e Devoluções por Produto/Mês

**Materialized view:** `analytics.mv_ai_desconto_devolucao_produto_mensal`.

**Origem:** `analytics.fact_venda_item`, `analytics.fact_venda` e `analytics.dim_loja`.

**Campos:** `mes`, `associado_id`, `loja_id`, `cnpj`, `produto_id`, `produto`, `qtd_liquida`, `receita_liquida_item`, `desconto_manual`, `desconto_automatico`, `desconto_total`, `valor_devolucao`, `qtd_devolvida`.

**Uso:** ranking de produtos com maior desconto ou devolução.

### 6.10 Materialized Views da IA Versionadas

**Materialized views usadas pelo backend:**

- `analytics.mv_ai_sazonalidade_dia_semana`.
- `analytics.mv_ai_desconto_devolucao_diario`.
- `analytics.mv_ai_desconto_devolucao_produto_mensal`.

**Status:** criação versionada em `bi/sql/06_ai_kpis.sql`; refresh versionado em `app/scripts/refresh-bi-kpis.sh`.

**Campos esperados pelo backend:**

```sql
-- analytics.mv_ai_sazonalidade_dia_semana
data,
associado_id,
loja_id,
cnpj,
dia_semana,
nome_dia_semana,
qtd_cupons,
faturamento_liquido,
ticket_medio

-- analytics.mv_ai_desconto_devolucao_diario
data,
associado_id,
loja_id,
qtd_cupons,
faturamento_liquido,
desconto_manual,
desconto_automatico,
desconto_total,
percentual_desconto,
valor_devolucao,
percentual_devolucao

-- analytics.mv_ai_desconto_devolucao_produto_mensal
mes,
produto_id,
produto,
qtd_liquida,
receita_liquida_item,
desconto_manual,
desconto_automatico,
desconto_total,
valor_devolucao,
qtd_devolvida,
loja_id
```

**Validação necessária:** após aplicar `bi/sql/06_ai_kpis.sql`, confirmar contagem de linhas e data máxima das três MVs no banco implantado.

## 7. Queries Locais da IA

As respostas da IA usam rotas locais quando possível, sem chamar OpenAI, para evitar lentidão e reduzir risco de resposta inventada.

### 7.1 Faturamento Total

```sql
select
  coalesce(sum(faturamento_liquido), 0) as faturamento,
  coalesce(sum(qtd_cupons), 0) as cupons,
  case when sum(qtd_cupons) = 0 then 0 else sum(faturamento_liquido) / sum(qtd_cupons) end as ticket_medio
from analytics.mv_kpi_faturamento_diario
where data between %(data_inicio)s and %(data_fim)s
{loja_filter};
```

### 7.2 Ticket Médio

Mesma base de faturamento total, retornando principalmente `ticket_medio`.

### 7.3 Séries de Faturamento por Dia e por Mês

**Faturamento por dia:**

```sql
select *
from (
  select
    data,
    sum(faturamento_liquido) as faturamento,
    sum(qtd_cupons) as cupons,
    case when sum(qtd_cupons) = 0 then 0 else sum(faturamento_liquido) / sum(qtd_cupons) end as ticket_medio
  from analytics.mv_kpi_faturamento_diario
  where data between %(data_inicio)s and %(data_fim)s
  {loja_filter}
  group by data
  order by data desc
  limit 366
) diario
order by data;
```

**Faturamento por mês:**

```sql
select
  mes,
  sum(faturamento_liquido) as faturamento,
  sum(qtd_cupons) as cupons,
  case when sum(qtd_cupons) = 0 then 0 else sum(faturamento_liquido) / sum(qtd_cupons) end as ticket_medio
from analytics.mv_kpi_faturamento_mensal
where mes between date_trunc('month', %(data_inicio)s::date)::date and date_trunc('month', %(data_fim)s::date)::date
{loja_filter}
group by mes
order by mes
limit 240;
```

**Uso:** perguntas como “faturamento por dia”, “cada dia”, “faturamento mensal” e “mês a mês”.

### 7.4 Faturamento por Loja

```sql
select
  loja_id,
  max(loja) as loja,
  sum(faturamento_liquido) as faturamento,
  sum(qtd_cupons) as cupons,
  case when sum(qtd_cupons) = 0 then 0 else sum(faturamento_liquido) / sum(qtd_cupons) end as ticket_medio
from analytics.mv_kpi_faturamento_loja
where data between %(data_inicio)s and %(data_fim)s
{loja_filter}
group by loja_id
order by faturamento desc;
```

**Uso:** “qual loja vendeu mais?”, “qual loja vendeu menos?”, “liste todas as lojas”.

### 7.5 Produtos com Lucro ou Prejuízo

```sql
select
  produto_id,
  max(produto) as produto,
  sum(qtd_vendida) as qtd_vendida,
  sum(receita_liquida_item) as receita,
  sum(custo_total_estimado) as custo,
  sum(lucro_bruto_estimado) as lucro,
  case when sum(receita_liquida_item) = 0 then null else sum(lucro_bruto_estimado) / sum(receita_liquida_item) end as margem
from analytics.mv_kpi_lucro_produto
where data between %(data_inicio)s and %(data_fim)s
{loja_filter}
group by produto_id
having sum(lucro_bruto_estimado) < 0 -- modo prejuízo
order by lucro asc
limit %(limit)s;
```

Para produtos com lucro, a condição muda para:

```sql
having sum(lucro_bruto_estimado) > 0
order by lucro desc
```

### 7.6 Produtos Estratégicos / Curva ABC

```sql
with produto as (
  select
    produto_id,
    max(produto) as produto,
    sum(qtd_vendida) as qtd_vendida,
    sum(receita_liquida_item) as receita,
    sum(lucro_bruto_estimado) as lucro,
    case when sum(receita_liquida_item) = 0 then null else sum(lucro_bruto_estimado) / sum(receita_liquida_item) end as margem
  from analytics.mv_ai_produto_mensal
  where mes between date_trunc('month', %(data_inicio)s::date)::date and date_trunc('month', %(data_fim)s::date)::date
  {loja_filter}
  group by produto_id
), abc as (
  select
    *,
    sum(receita) over () as receita_total,
    sum(receita) over (order by receita desc rows unbounded preceding) as receita_acumulada
  from produto
)
select
  produto_id,
  produto,
  qtd_vendida,
  receita,
  lucro,
  margem,
  case
    when receita_total = 0 then 'C'
    when receita_acumulada / receita_total <= 0.80 then 'A'
    when receita_acumulada / receita_total <= 0.95 then 'B'
    else 'C'
  end as curva_abc_faturamento
from abc
order by receita desc
limit 15;
```

**Uso:** perguntas sobre curva ABC, produto líder, produtos estratégicos, crescimento e queda.

### 7.7 Recomendação de Produtos

```sql
with produto as (
  select
    produto_id,
    max(produto) as produto,
    sum(qtd_vendida) as qtd_vendida,
    sum(receita_liquida_item) as receita,
    sum(custo_total_estimado) as custo,
    sum(lucro_bruto_estimado) as lucro,
    case when sum(receita_liquida_item) = 0 then null else sum(lucro_bruto_estimado) / sum(receita_liquida_item) end as margem
  from analytics.mv_kpi_lucro_produto
  where data between %(data_inicio)s and %(data_fim)s
  {loja_filter}
  group by produto_id
), foco as (
  select 'focar' as tipo, produto_id, produto, qtd_vendida, receita, custo, lucro, margem,
         (lucro * 0.60 + receita * 0.30 + qtd_vendida * 0.10) as score
  from produto
  where receita > 0 and lucro > 0 and qtd_vendida > 0
  order by lucro desc, receita desc
  limit 5
), corrigir as (
  select 'corrigir' as tipo, produto_id, produto, qtd_vendida, receita, custo, lucro, margem, lucro as score
  from produto
  where lucro < 0 and receita > 0
  order by lucro asc
  limit 5
)
select * from foco
union all
select * from corrigir
order by tipo desc, score desc;
```

**Uso:** perguntas como “qual produto focar”, “priorizar”, “oportunidade” e “recomendação”.

**Observação:** a recomendação é gerencial e baseada em lucro estimado, receita e quantidade vendida; não substitui validação comercial/estoque.

### 7.8 Clientes Ativos

```sql
with periodo_cliente as (
  select
    cliente_id,
    max(cliente) as cliente,
    sum(qtd_cupons) as cupons,
    sum(faturamento_liquido) as faturamento,
    case when sum(qtd_cupons) = 0 then 0 else sum(faturamento_liquido) / sum(qtd_cupons) end as ticket_medio,
    min(primeira_compra_loja) as primeira_compra,
    max(data) as ultima_compra
  from analytics.mv_ai_cliente_diario
  where data between %(data_inicio)s and %(data_fim)s
  {loja_filter}
  group by cliente_id
)
select
  count(*) as clientes_ativos,
  count(*) filter (where primeira_compra between %(data_inicio)s and %(data_fim)s) as clientes_novos,
  count(*) filter (where cupons > 1) as clientes_recorrentes,
  null::numeric as clientes_inativos,
  coalesce(sum(faturamento), 0) as faturamento_clientes,
  case when sum(cupons) = 0 then 0 else sum(faturamento) / sum(cupons) end as ticket_medio_clientes
from periodo_cliente;
```

**Observação:** clientes inativos não são calculados na lista rápida para evitar query pesada.

### 7.9 Vendedores

```sql
select * from (
  select
    vendedor_id,
    vendedor,
    sum(valor_vendido) as valor_vendido,
    sum(qtd_vendas) as qtd_vendas,
    case when sum(qtd_vendas) = 0 then 0 else sum(valor_vendido) / sum(qtd_vendas) end as ticket_medio,
    case when sum(qtd_vendas) = 0 then 0 else sum(qtd_itens_vendidos) / sum(qtd_vendas) end as itens_por_venda,
    sum(qtd_skus) as qtd_skus,
    sum(lucro_bruto_estimado) as lucro,
    case when sum(valor_vendido) = 0 then null else sum(lucro_bruto_estimado) / sum(valor_vendido) end as margem,
    sum(desconto_manual) as desconto_manual,
    sum(desconto_automatico) as desconto_automatico,
    sum(valor_devolucao) as valor_devolucao
  from analytics.mv_ai_vendedor_diario
  where data between %(data_inicio)s and %(data_fim)s
  {loja_filter}
  group by vendedor_id, vendedor
) vendedores
order by valor_vendido desc
limit 50;
```

Para perguntas de margem, o `order by` muda para margem/lucro e aplica filtro mínimo de venda:

```sql
where valor_vendido >= 100
```

### 7.10 Horários

```sql
select
  hora,
  max(faixa_horaria) as faixa_horaria,
  sum(faturamento_liquido) as faturamento,
  sum(qtd_cupons) as cupons,
  case when sum(qtd_cupons) = 0 then 0 else sum(faturamento_liquido) / sum(qtd_cupons) end as ticket_medio
from analytics.mv_ai_vendas_horario
where data between %(data_inicio)s and %(data_fim)s
{loja_filter}
group by hora
order by faturamento desc
limit 24;
```

### 7.11 Alertas

```sql
select
  tipo_alerta,
  severidade,
  max(titulo) as titulo,
  max(descricao) as descricao,
  count(*) as ocorrencias,
  sum(valor_atual) as valor_total,
  max(data_ref) as ultima_data
from analytics.mv_ai_alertas_operacionais
where data_ref between %(data_inicio)s and %(data_fim)s
{loja_filter}
group by tipo_alerta, severidade
order by case severidade when 'alta' then 1 when 'media' then 2 else 3 end, ocorrencias desc
limit 10;
```

### 7.12 CMV Percentual / DRE Gerencial

```sql
select
  coalesce(sum(receita_liquida_item), 0) as receita_liquida,
  coalesce(sum(custo_total_estimado), 0) as cmv_estimado,
  coalesce(sum(lucro_bruto_total), 0) as lucro_bruto_estimado,
  case when sum(receita_liquida_item) = 0 then null else sum(custo_total_estimado) / sum(receita_liquida_item) end as cmv_percentual,
  case when sum(receita_liquida_item) = 0 then null else sum(lucro_bruto_total) / sum(receita_liquida_item) end as margem_bruta
from analytics.mv_kpi_lucro_total_diario
where data between %(data_inicio)s and %(data_fim)s
{loja_filter};
```

**Observação:** DRE completa contábil não está disponível; a resposta é parcial/gerencial.

## 8. Queries Não Homologadas ou Pendentes

### 8.0 Auditoria de Venda Válida e Ticket Médio

```sql
\set data_inicio '2026-06-01'
\set data_fim '2026-07-01'
\i bi/sql/12_validate_valid_sale_ticket.sql
```

**Fonte principal da auditoria:** `bronze.vendas_cab`.

**Regra validada:** vendas válidas são `st_caixa in ('PA', 'DP')`; faturamento líquido é `sum(vlr_liquido - vlr_devolucao)`; ticket médio é `faturamento_liquido / count(*)` sobre vendas válidas.

**Resultado de referência registrado para `2026-06-01` a `2026-07-01`:** `758737` vendas válidas, faturamento válido `45778779.01`, ticket médio válido `60.3355036198313777`. Diferença residual observada contra `analytics.mv_kpi_faturamento_diario`: `1` cupom e `409.31` em faturamento, pendente de consolidação bronze/gold e sincronização com fonte live.

**Observação operacional:** se o FDW `cliente_farmacias` estiver com erro de autenticação ou timeout, esta auditoria continua útil por usar a bronze local já carregada.

### 8.1 Estoque Atual

**Status:** pendente.

**Tabela provável:** `vendas.produto_estoq`.

**Regra:** a confirmar com ERP.

### 8.2 Giro de Estoque

**Status:** pendente.

**Dependências:** estoque médio ou saldo confiável, CMV/quantidade vendida e janela de tempo.

### 8.3 Ruptura

**Status:** pendente.

**Dependências:** estoque, demanda esperada e regra de produto ativo.

### 8.4 Categoria de Produto

**Status:** pendente.

Nas views atuais não foi identificado campo de categoria exposto para o dashboard.

## 9. Observações de Performance

1. As queries do dashboard devem preferir materialized views locais `analytics.mv_*`.
2. O filtro por CNPJ consulta `analytics.dim_loja`; em produção ela deve apontar para `silver.dim_loja`, não diretamente para FDW.
3. Queries de produto/margem podem ler MVs grandes, especialmente `analytics.mv_kpi_lucro_produto`.
4. Refresh de MVs pesadas não deve rodar em horário comercial sem estratégia de concorrência, pois pode bloquear consultas.
5. Para 200 usuários simultâneos, recomenda-se cache, pooler e timeouts antes de aumentar `max_connections`.
6. Auditorias e refreshes que dependem de fatos grandes ainda podem ser afetados por autenticação/timeout do FDW; priorizar bronze/gold local para fatos no próximo ciclo.

## 10. Arquivos Técnicos de Origem

| Arquivo | Conteúdo |
|---|---|
| `bi/sql/01_analytics_schema.sql` | Views base, fatos e dimensões |
| `bi/sql/01_local_dimensions.sql` | Dimensões locais em `silver` e função `analytics.refresh_local_dimensions(include_large boolean)` |
| `bi/sql/02_kpi_views.sql` | Views base dos KPIs |
| `bi/sql/05_materialized_kpis.sql` | Materialized views do dashboard |
| `bi/sql/06_ai_kpis.sql` | Materialized views da IA |
| `bi/sql/07_operational_kpis.sql` | KPI operacional diário |
| `bi/sql/08_bronze_sales.sql` | Cópia local bronze de vendas, itens e serviços por janela |
| `bi/sql/09_bronze_fact_views.sql` | Migração opt-in de facts para bronze local, somente após cobertura completa |
| `bi/sql/10_valid_sale_kpis.sql` | Regra incremental de venda válida `PA/DP` nos KPIs executivos |
| `bi/sql/11_operational_kpis_bronze.sql` | MV operacional a partir da bronze local para evitar timeout em FDW |
| `bi/sql/12_validate_valid_sale_ticket.sql` | Auditoria local de venda válida, faturamento e ticket médio |
| `app/backend/app/services/metrics.py` | Queries dos endpoints de métricas |
| `app/backend/app/routes/metrics.py` | Exposição dos endpoints HTTP |
| `app/backend/app/services/question_answering.py` | Queries locais da IA |
| `app/backend/app/db.py` | Montagem de filtros e pool de conexão |
