-- Cria camada analitica base. Nao altera o schema vendas.

create schema if not exists analytics;

create or replace view analytics.dim_associado as
select
  id as associado_id,
  id_associado_interno,
  nome,
  cnpj,
  status,
  data_inc,
  matriz,
  regiao,
  porte,
  software
from vendas.associado;

create or replace view analytics.dim_loja as
select
  id as loja_id,
  id_associado as associado_id,
  id_loja_interno,
  nome,
  cnpj
from vendas.loja;

create or replace view analytics.dim_cliente as
select
  id as cliente_id,
  id_associado as associado_id,
  id_cliente_interno,
  nome
from vendas.cliente;

create or replace view analytics.dim_colaborador as
select
  id as colaborador_id,
  id_associado as associado_id,
  id_colaborador_interno,
  nome
from vendas.colaborador;

create or replace view analytics.dim_produto as
select
  id as produto_id,
  id_associado as associado_id,
  id_produto_interno,
  nome,
  gtin,
  preco_bruto,
  preco_liquido,
  custo_ult_entrada
from vendas.produto;

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
  vc.st_caixa = 'DV' as is_devolucao_total
from vendas.vendas_cab vc;

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
from vendas.vendas_item vi
left join vendas.produto p on p.id = vi.id_produto;

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
