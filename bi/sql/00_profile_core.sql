-- Perfilamento inicial dos campos criticos.
-- Execute no banco restaurado: psql -U postgres -d vendas -f C:\Banco\bi\sql\00_profile_core.sql

\echo '01. Periodo disponivel em vendas_cab'
select
  min(data) as primeira_venda,
  max(data) as ultima_venda,
  count(*) as qtd_cabecalhos
from vendas.vendas_cab;

\echo '02. Distribuicao por status/st_caixa/tipo/origem'
select
  coalesce(status, '<null>') as status,
  coalesce(st_caixa, '<null>') as st_caixa,
  coalesce(tipo_venda, '<null>') as tipo_venda,
  coalesce(origem, '<null>') as origem,
  count(*) as qtd_cupons,
  sum(vlr_liquido) as faturamento_liquido,
  sum(vlr_produto) as faturamento_produto,
  sum(vlr_servico) as faturamento_servico,
  sum(vlr_devolucao) as valor_devolucao
from vendas.vendas_cab
group by 1, 2, 3, 4
order by qtd_cupons desc
limit 100;

\echo '03. Valores negativos, zerados e devolucao'
select
  count(*) filter (where vlr_liquido < 0) as cupons_liquido_negativo,
  count(*) filter (where vlr_liquido = 0) as cupons_liquido_zero,
  count(*) filter (where vlr_devolucao > 0) as cupons_com_devolucao,
  count(*) filter (where vlr_produto = 0 and vlr_servico > 0) as cupons_apenas_servico,
  count(*) filter (where cpf_nf is not null and btrim(cpf_nf) <> '') as cupons_com_cpf_nf
from vendas.vendas_cab;

\echo '04. Granularidade de cupom'
select
  count(*) as linhas,
  count(distinct id) as ids_distintos,
  count(distinct (id_associado, id_loja, nro_venda, data, nro_caixa)) as cupons_operacionais_distintos,
  count(distinct ticket) filter (where ticket is not null) as tickets_distintos
from vendas.vendas_cab;

\echo '05. Periodo e volume em vendas_item'
select
  count(*) as qtd_itens,
  count(distinct id_venda) as vendas_com_item,
  sum(qtd_venda) as qtd_vendida_bruta,
  sum(qtd_devol) as qtd_devolvida,
  sum(qtd_venda - qtd_devol) as qtd_liquida,
  sum(vlr_venda) as valor_venda_itens,
  sum(vlr_devol) as valor_devolucao_itens
from vendas.vendas_item;

\echo '06. Validacao se vlr_venda parece total ou unitario'
select
  count(*) as itens_amostrados,
  avg(abs(vlr_venda - (qtd_venda * vlr_unitario))) as erro_medio_total_item,
  sum(case when abs(vlr_venda - (qtd_venda * vlr_unitario)) <= 0.05 then 1 else 0 end) as parece_total,
  sum(case when abs(vlr_venda - vlr_unitario) <= 0.05 then 1 else 0 end) as parece_unitario
from (
  select qtd_venda, vlr_unitario, vlr_venda
  from vendas.vendas_item
  where qtd_venda > 0 and vlr_unitario > 0 and vlr_venda > 0
  limit 100000
) s;

\echo '07. Disponibilidade de custos em vendas_item e produto'
select
  count(*) as qtd_itens,
  count(*) filter (where vi.custo_real > 0) as com_custo_real,
  count(*) filter (where vi.custo_medio > 0) as com_custo_medio,
  count(*) filter (where vi.custo_ult > 0) as com_custo_ult,
  count(*) filter (where p.custo_ult_entrada > 0) as com_custo_produto,
  count(*) filter (where coalesce(nullif(vi.custo_real, 0), nullif(vi.custo_medio, 0), nullif(vi.custo_ult, 0), nullif(p.custo_ult_entrada, 0)) is not null) as com_algum_custo
from vendas.vendas_item vi
left join vendas.produto p on p.id = vi.id_produto;

\echo '08. Produtos vendidos com custo ausente na amostra'
select
  vi.id_produto,
  coalesce(p.nome, vi.nome_produto) as produto,
  count(*) as qtd_linhas,
  sum(vi.qtd_venda - vi.qtd_devol) as qtd_liquida,
  sum(vi.vlr_venda - vi.vlr_devol) as venda_liquida
from vendas.vendas_item vi
left join vendas.produto p on p.id = vi.id_produto
where coalesce(nullif(vi.custo_real, 0), nullif(vi.custo_medio, 0), nullif(vi.custo_ult, 0), nullif(p.custo_ult_entrada, 0)) is null
group by 1, 2
order by venda_liquida desc nulls last
limit 50;

\echo '09. Comparacao entre cabecalho e itens por amostra de vendas'
with amostra as (
  select id, vlr_liquido, vlr_produto, vlr_servico, vlr_devolucao
  from vendas.vendas_cab
  order by id desc
  limit 50000
), itens as (
  select
    id_venda,
    sum(vlr_venda) as soma_itens,
    sum(vlr_devol) as soma_devol_item,
    sum(qtd_venda - qtd_devol) as qtd_liquida
  from vendas.vendas_item
  where id_venda in (select id from amostra)
  group by id_venda
)
select
  count(*) as vendas_amostradas,
  avg(abs(a.vlr_produto - coalesce(i.soma_itens, 0))) as dif_media_produto_vs_itens,
  avg(abs(a.vlr_devolucao - coalesce(i.soma_devol_item, 0))) as dif_media_devolucao,
  sum(a.vlr_liquido) as cab_liquido,
  sum(coalesce(i.soma_itens, 0)) as item_venda
from amostra a
left join itens i on i.id_venda = a.id;

\echo '10. Periodo disponivel em notas de entrada'
select
  min(data_doc) as primeira_nf,
  max(data_doc) as ultima_nf,
  count(*) as qtd_notas,
  sum(vlr_total) as valor_total_notas
from vendas.nf_entrada_cab;

\echo '11. Custos de compra por item'
select
  count(*) as qtd_itens_compra,
  count(*) filter (where vlr_unitario > 0) as com_vlr_unitario,
  count(*) filter (where vlr_total > 0) as com_vlr_total,
  count(distinct id_produto) as produtos_com_compra
from vendas.nf_entrada_item;
