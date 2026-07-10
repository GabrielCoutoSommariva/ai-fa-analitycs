-- MV operacional lendo da bronze local para evitar timeout FDW.
-- Cobertura limitada ao periodo carregado em bronze.vendas_*.

create schema if not exists analytics;

drop materialized view if exists analytics.mv_kpi_operacional_diario;

create materialized view analytics.mv_kpi_operacional_diario as
with vendas_validas as (
  select *
  from bronze.vendas_cab
  where data <= current_date
    and st_caixa in ('PA', 'DP')
), itens_por_cupom as (
  select
    vc.data,
    vc.id_associado as associado_id,
    vc.id_loja as loja_id,
    vc.id as venda_id,
    coalesce(sum(vi.qtd_venda - vi.qtd_devol), 0) as qtd_itens
  from vendas_validas vc
  left join bronze.vendas_item vi on vi.id_venda = vc.id
  group by 1, 2, 3, 4
), itens_diario as (
  select
    vc.data,
    vi.id_associado as associado_id,
    vi.id_loja as loja_id,
    sum(coalesce(vi.vlr_desc_usu, 0)) as desconto_manual,
    sum(coalesce(vi.vlr_desc_sist, 0)) as desconto_automatico,
    sum(coalesce(vi.vlr_desc_usu, 0) + coalesce(vi.vlr_desc_sist, 0)) as desconto_total,
    sum(coalesce(vi.vlr_venda - vi.vlr_devol, 0)) as receita_liquida_item,
    sum((vi.qtd_venda - vi.qtd_devol) * coalesce(nullif(vi.custo_real, 0), nullif(vi.custo_medio, 0), nullif(vi.custo_ult, 0), nullif(p.custo_ult_entrada, 0), 0)) as custo_total_estimado
  from bronze.vendas_item vi
  join vendas_validas vc on vc.id = vi.id_venda
  left join analytics.dim_produto p on p.produto_id = vi.id_produto
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
    vc.data,
    vs.id_associado as associado_id,
    vs.id_loja as loja_id,
    count(*) as linhas_servico,
    count(distinct vs.id_venda) as cupons_com_servico,
    sum(coalesce(vs.valor, 0)) as valor_servico,
    sum(coalesce(vs.vlr_desc, 0)) as desconto_servico,
    sum(coalesce(vs.custo, 0)) as custo_servico
  from bronze.vendas_serv vs
  join vendas_validas vc on vc.id = vs.id_venda
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
