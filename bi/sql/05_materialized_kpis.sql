-- Materializacoes para acelerar o dashboard.
-- Recrie/atualize quando os dados do schema vendas forem recarregados.

create schema if not exists analytics;

drop materialized view if exists analytics.mv_kpi_lucro_total_diario;
drop materialized view if exists analytics.mv_kpi_lucro_produto_total_loja;
drop materialized view if exists analytics.mv_kpi_lucro_produto;
drop materialized view if exists analytics.mv_kpi_faturamento_loja;
drop materialized view if exists analytics.mv_kpi_itens_vendidos;
drop materialized view if exists analytics.mv_kpi_cupons;
drop materialized view if exists analytics.mv_kpi_faturamento_mensal;
drop materialized view if exists analytics.mv_kpi_faturamento_diario;

create materialized view analytics.mv_kpi_faturamento_diario as
select *
from analytics.kpi_faturamento_diario;

create index idx_mv_kpi_faturamento_diario_data on analytics.mv_kpi_faturamento_diario (data);
create index idx_mv_kpi_faturamento_diario_data_loja on analytics.mv_kpi_faturamento_diario (data, loja_id);
create index idx_mv_kpi_faturamento_diario_loja on analytics.mv_kpi_faturamento_diario (loja_id);

create materialized view analytics.mv_kpi_faturamento_mensal as
select *
from analytics.kpi_faturamento_mensal;

create index idx_mv_kpi_faturamento_mensal_mes on analytics.mv_kpi_faturamento_mensal (mes);
create index idx_mv_kpi_faturamento_mensal_mes_loja on analytics.mv_kpi_faturamento_mensal (mes, loja_id);
create index idx_mv_kpi_faturamento_mensal_loja on analytics.mv_kpi_faturamento_mensal (loja_id);

create materialized view analytics.mv_kpi_cupons as
select *
from analytics.kpi_cupons;

create index idx_mv_kpi_cupons_data on analytics.mv_kpi_cupons (data);
create index idx_mv_kpi_cupons_data_loja on analytics.mv_kpi_cupons (data, loja_id);
create index idx_mv_kpi_cupons_loja on analytics.mv_kpi_cupons (loja_id);

create materialized view analytics.mv_kpi_itens_vendidos as
select *
from analytics.kpi_itens_vendidos;

create index idx_mv_kpi_itens_vendidos_data on analytics.mv_kpi_itens_vendidos (data);
create index idx_mv_kpi_itens_vendidos_data_loja on analytics.mv_kpi_itens_vendidos (data, loja_id);
create index idx_mv_kpi_itens_vendidos_loja on analytics.mv_kpi_itens_vendidos (loja_id);

create materialized view analytics.mv_kpi_faturamento_loja as
select *
from analytics.kpi_faturamento_loja;

create index idx_mv_kpi_faturamento_loja_data on analytics.mv_kpi_faturamento_loja (data);
create index idx_mv_kpi_faturamento_loja_data_loja on analytics.mv_kpi_faturamento_loja (data, loja_id);
create index idx_mv_kpi_faturamento_loja_loja on analytics.mv_kpi_faturamento_loja (loja_id);

create materialized view analytics.mv_kpi_lucro_produto as
select *
from analytics.kpi_lucro_produto;

create index idx_mv_kpi_lucro_produto_data on analytics.mv_kpi_lucro_produto (data);
create index idx_mv_kpi_lucro_produto_data_loja on analytics.mv_kpi_lucro_produto (data, loja_id);
create index idx_mv_kpi_lucro_produto_loja on analytics.mv_kpi_lucro_produto (loja_id);
create index idx_mv_kpi_lucro_produto_produto on analytics.mv_kpi_lucro_produto (produto_id);
create index idx_mv_kpi_lucro_produto_lucro on analytics.mv_kpi_lucro_produto (lucro_bruto_estimado);

create materialized view analytics.mv_kpi_lucro_produto_total_loja as
select
  associado_id,
  loja_id,
  produto_id,
  max(produto) as produto,
  sum(qtd_vendida) as qtd_vendida,
  sum(receita_liquida_item) as receita_liquida_item,
  sum(custo_total_estimado) as custo_total_estimado,
  sum(lucro_bruto_estimado) as lucro_bruto_estimado,
  case
    when sum(receita_liquida_item) = 0 then null
    else sum(lucro_bruto_estimado) / sum(receita_liquida_item)
  end as margem_bruta_percentual
from analytics.mv_kpi_lucro_produto
group by 1, 2, 3;

create index idx_mv_kpi_lucro_produto_total_loja_loja on analytics.mv_kpi_lucro_produto_total_loja (loja_id);
create index idx_mv_kpi_lucro_produto_total_loja_produto on analytics.mv_kpi_lucro_produto_total_loja (produto_id);
create index idx_mv_kpi_lucro_produto_total_loja_lucro on analytics.mv_kpi_lucro_produto_total_loja (lucro_bruto_estimado);

create materialized view analytics.mv_kpi_lucro_total_diario as
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

create index idx_mv_kpi_lucro_total_diario_data on analytics.mv_kpi_lucro_total_diario (data);
create index idx_mv_kpi_lucro_total_diario_data_loja on analytics.mv_kpi_lucro_total_diario (data, loja_id);
create index idx_mv_kpi_lucro_total_diario_loja on analytics.mv_kpi_lucro_total_diario (loja_id);

analyze analytics.mv_kpi_faturamento_diario;
analyze analytics.mv_kpi_faturamento_mensal;
analyze analytics.mv_kpi_cupons;
analyze analytics.mv_kpi_itens_vendidos;
analyze analytics.mv_kpi_faturamento_loja;
analyze analytics.mv_kpi_lucro_produto;
analyze analytics.mv_kpi_lucro_produto_total_loja;
analyze analytics.mv_kpi_lucro_total_diario;
