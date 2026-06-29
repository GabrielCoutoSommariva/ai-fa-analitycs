-- KPIs iniciais. As regras de status ainda devem ser validadas em 00_profile_core.sql.

create schema if not exists analytics;

create or replace view analytics.kpi_faturamento_diario as
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

create or replace view analytics.kpi_faturamento_mensal as
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

create or replace view analytics.kpi_ticket_medio as
select
  data,
  associado_id,
  loja_id,
  count(*) as qtd_cupons,
  sum(vlr_liquido_ajustado) as faturamento_liquido,
  case when count(*) = 0 then 0 else sum(vlr_liquido_ajustado) / count(*) end as ticket_medio
from analytics.fact_venda
group by 1, 2, 3;

create or replace view analytics.kpi_cupons as
select
  data,
  associado_id,
  loja_id,
  count(*) as qtd_cupons,
  count(distinct nro_venda) as nro_venda_distintos,
  count(distinct ticket) filter (where ticket is not null) as tickets_distintos
from analytics.fact_venda
group by 1, 2, 3;

create or replace view analytics.kpi_itens_vendidos as
select
  fv.data,
  fvi.associado_id,
  fvi.loja_id,
  count(*) as linhas_item,
  count(distinct fvi.venda_id) as cupons_com_item,
  sum(fvi.qtd_liquida) as qtd_itens_vendidos,
  case when count(distinct fvi.venda_id) = 0 then 0 else sum(fvi.qtd_liquida) / count(distinct fvi.venda_id) end as itens_por_cupom
from analytics.fact_venda_item fvi
join analytics.fact_venda fv on fv.venda_id = fvi.venda_id
group by 1, 2, 3;

create or replace view analytics.kpi_faturamento_loja as
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

create or replace view analytics.kpi_lucro_produto as
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

create or replace view analytics.kpi_produtos_mais_lucrativos as
select *
from analytics.kpi_lucro_produto
where lucro_bruto_estimado > 0
order by lucro_bruto_estimado desc;

create or replace view analytics.kpi_produtos_menos_lucrativos as
select *
from analytics.kpi_lucro_produto
where lucro_bruto_estimado is not null
order by lucro_bruto_estimado asc;

create or replace view analytics.kpi_produtos_prejuizo as
select *
from analytics.kpi_lucro_produto
where lucro_bruto_estimado < 0
order by lucro_bruto_estimado asc;

create or replace view analytics.kpi_lucro_total_diario as
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
from analytics.kpi_lucro_produto
group by 1, 2, 3;
