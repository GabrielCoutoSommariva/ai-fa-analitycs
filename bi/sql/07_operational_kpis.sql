create schema if not exists analytics;

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

drop materialized view if exists analytics.mv_kpi_operacional_diario;

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

analyze analytics.mv_kpi_operacional_diario;
