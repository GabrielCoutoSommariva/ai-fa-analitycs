-- Troca opt-in das facts analytics.* para ler a camada bronze local.
-- Nao execute em producao antes de validar que bronze.vendas_* cobre o periodo esperado.

create schema if not exists analytics;
create schema if not exists bronze;

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
from bronze.vendas_cab vc;

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
  coalesce(nullif(vi.custo_real, 0), nullif(vi.custo_medio, 0), nullif(vi.custo_ult, 0), nullif(p.custo_ult_entrada, 0)) as custo_unitario_base,
  (vi.qtd_venda - vi.qtd_devol) * coalesce(nullif(vi.custo_real, 0), nullif(vi.custo_medio, 0), nullif(vi.custo_ult, 0), nullif(p.custo_ult_entrada, 0), 0) as custo_total_base,
  (vi.vlr_venda - vi.vlr_devol) - ((vi.qtd_venda - vi.qtd_devol) * coalesce(nullif(vi.custo_real, 0), nullif(vi.custo_medio, 0), nullif(vi.custo_ult, 0), nullif(p.custo_ult_entrada, 0), 0)) as lucro_bruto_estimado,
  vi.tributacao,
  vi.icms,
  vi.perc_comissao,
  vi.vlr_comissao,
  vi.fcia_popular,
  vi.pre_vencido,
  vi.uso_continuo,
  vi.bloq_sngpc,
  vi.bloq_compra
from bronze.vendas_item vi
left join analytics.dim_produto p on p.produto_id = vi.id_produto;

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
from bronze.vendas_serv vs;
