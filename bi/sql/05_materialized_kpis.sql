-- Materializacoes para acelerar o dashboard.
-- Recrie/atualize quando os dados do schema vendas forem recarregados.

create schema if not exists analytics;

drop materialized view if exists analytics.mv_kpi_lucro_total_diario;
drop materialized view if exists analytics.mv_kpi_operacional_diario;
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

create materialized view analytics.mv_kpi_operacional_diario as
with itens_por_cupom as (
  select
    fv.data,
    fv.associado_id,
    fv.loja_id,
    fv.venda_id,
    coalesce(sum(fvi.qtd_liquida), 0) as qtd_itens
  from analytics.fact_venda fv
  left join analytics.fact_venda_item fvi on fvi.venda_id = fv.venda_id
  where fv.data <= current_date and fv.is_venda_valida
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
  where fv.data <= current_date and fv.is_venda_valida
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
  where fv.data <= current_date and fv.is_venda_valida
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

create index idx_mv_kpi_operacional_diario_data on analytics.mv_kpi_operacional_diario (data);
create index idx_mv_kpi_operacional_diario_data_loja on analytics.mv_kpi_operacional_diario (data, loja_id);
create index idx_mv_kpi_operacional_diario_loja on analytics.mv_kpi_operacional_diario (loja_id);

analyze analytics.mv_kpi_faturamento_diario;
analyze analytics.mv_kpi_faturamento_mensal;
analyze analytics.mv_kpi_cupons;
analyze analytics.mv_kpi_itens_vendidos;
analyze analytics.mv_kpi_faturamento_loja;
analyze analytics.mv_kpi_lucro_produto;
analyze analytics.mv_kpi_lucro_produto_total_loja;
analyze analytics.mv_kpi_lucro_total_diario;
analyze analytics.mv_kpi_operacional_diario;
