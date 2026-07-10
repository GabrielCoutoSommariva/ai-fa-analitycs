-- KPIs AI-only para respostas consultivas. Nao altera o dashboard.
-- Mantem dados por loja para aplicar o mesmo filtro de CNPJ autorizado da aplicacao.

create schema if not exists analytics;

drop materialized view if exists analytics.mv_ai_alertas_operacionais;
drop materialized view if exists analytics.mv_ai_desconto_devolucao_produto_mensal;
drop materialized view if exists analytics.mv_ai_desconto_devolucao_diario;
drop materialized view if exists analytics.mv_ai_sazonalidade_dia_semana;
drop materialized view if exists analytics.mv_ai_produto_mensal;
drop materialized view if exists analytics.mv_ai_cliente_diario;
drop materialized view if exists analytics.mv_ai_vendas_horario;
drop materialized view if exists analytics.mv_ai_vendedor_diario;
drop materialized view if exists analytics.mv_ai_resumo_executivo_diario;

create materialized view analytics.mv_ai_resumo_executivo_diario as
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

create index idx_mv_ai_resumo_exec_data_loja on analytics.mv_ai_resumo_executivo_diario (data, loja_id);
create index idx_mv_ai_resumo_exec_loja on analytics.mv_ai_resumo_executivo_diario (loja_id);
create index idx_mv_ai_resumo_exec_cnpj on analytics.mv_ai_resumo_executivo_diario (cnpj);

create materialized view analytics.mv_ai_vendedor_diario as
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
where fv.data <= current_date and fv.is_venda_valida
group by 1, 2, 3, 4, 5, 6;

create index idx_mv_ai_vendedor_data_loja on analytics.mv_ai_vendedor_diario (data, loja_id);
create index idx_mv_ai_vendedor_loja on analytics.mv_ai_vendedor_diario (loja_id);
create index idx_mv_ai_vendedor_vendedor on analytics.mv_ai_vendedor_diario (vendedor_id);
create index idx_mv_ai_vendedor_valor on analytics.mv_ai_vendedor_diario (valor_vendido);

create materialized view analytics.mv_ai_vendas_horario as
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
where fv.data <= current_date and fv.is_venda_valida and fv.hora is not null
group by 1, 2, 3, 4, 5, 6, 7;

create index idx_mv_ai_vendas_horario_data_loja on analytics.mv_ai_vendas_horario (data, loja_id);
create index idx_mv_ai_vendas_horario_loja on analytics.mv_ai_vendas_horario (loja_id);
create index idx_mv_ai_vendas_horario_hora on analytics.mv_ai_vendas_horario (hora);

create materialized view analytics.mv_ai_alertas_operacionais as
with resumo as (
  select
    data,
    associado_id,
    loja_id,
    cnpj,
    faturamento_liquido,
    qtd_cupons,
    ticket_medio,
    lucro_bruto_total,
    margem_bruta_percentual,
    lag(faturamento_liquido) over (partition by loja_id order by data) as faturamento_dia_anterior,
    avg(ticket_medio) over (partition by loja_id order by data rows between 30 preceding and 1 preceding) as ticket_medio_30d
  from analytics.mv_ai_resumo_executivo_diario
), produto_prejuizo as (
  select
    p.data,
    p.associado_id,
    p.loja_id,
    regexp_replace(coalesce(l.cnpj, ''), '\D', '', 'g') as cnpj,
    count(*) as qtd_produtos,
    sum(p.lucro_bruto_estimado) as prejuizo_estimado
  from analytics.mv_kpi_lucro_produto p
  left join analytics.dim_loja l on l.loja_id = p.loja_id
  where p.data <= current_date and p.lucro_bruto_estimado < 0
  group by 1, 2, 3, 4
), datas_futuras as (
  select
    fv.data,
    fv.associado_id,
    fv.loja_id,
    regexp_replace(coalesce(l.cnpj, ''), '\D', '', 'g') as cnpj,
    count(*) as qtd_vendas
  from analytics.fact_venda fv
  left join analytics.dim_loja l on l.loja_id = fv.loja_id
  where fv.data > current_date and fv.is_venda_valida
  group by 1, 2, 3, 4
)
select
  data as data_ref,
  associado_id,
  loja_id,
  cnpj,
  'queda_faturamento'::text as tipo_alerta,
  case when faturamento_liquido <= faturamento_dia_anterior * 0.5 then 'alta' else 'media' end as severidade,
  'Queda de faturamento'::text as titulo,
  'Faturamento do dia ficou pelo menos 30% abaixo do dia anterior.'::text as descricao,
  faturamento_liquido as valor_atual,
  faturamento_dia_anterior as valor_referencia
from resumo
where faturamento_dia_anterior > 0 and faturamento_liquido < faturamento_dia_anterior * 0.7
union all
select
  data,
  associado_id,
  loja_id,
  cnpj,
  'margem_baixa'::text,
  case when margem_bruta_percentual < 0 then 'alta' else 'media' end,
  'Margem baixa ou negativa'::text,
  'Margem bruta estimada abaixo de 10% no dia.'::text,
  margem_bruta_percentual,
  0.10::numeric
from resumo
where margem_bruta_percentual is not null and margem_bruta_percentual < 0.10
union all
select
  data,
  associado_id,
  loja_id,
  cnpj,
  'ticket_baixo'::text,
  'media'::text,
  'Ticket medio abaixo da media'::text,
  'Ticket medio ficou pelo menos 20% abaixo da media movel de 30 dias.'::text,
  ticket_medio,
  ticket_medio_30d
from resumo
where ticket_medio_30d > 0 and ticket_medio < ticket_medio_30d * 0.8
union all
select
  data,
  associado_id,
  loja_id,
  cnpj,
  'produtos_prejuizo'::text,
  case when prejuizo_estimado < -1000 then 'alta' else 'media' end,
  'Produtos vendidos com prejuizo'::text,
  'Ha produtos com lucro bruto estimado negativo no dia.'::text,
  prejuizo_estimado,
  qtd_produtos::numeric
from produto_prejuizo
union all
select
  data,
  associado_id,
  loja_id,
  cnpj,
  'data_futura'::text,
  'alta'::text,
  'Venda com data futura'::text,
  'Existem vendas com data posterior a data atual. Ignorar em KPIs executivos.'::text,
  qtd_vendas::numeric,
  null::numeric
from datas_futuras;

create index idx_mv_ai_alertas_data_loja on analytics.mv_ai_alertas_operacionais (data_ref, loja_id);
create index idx_mv_ai_alertas_loja on analytics.mv_ai_alertas_operacionais (loja_id);
create index idx_mv_ai_alertas_tipo on analytics.mv_ai_alertas_operacionais (tipo_alerta);
create index idx_mv_ai_alertas_severidade on analytics.mv_ai_alertas_operacionais (severidade);

create materialized view analytics.mv_ai_cliente_diario as
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
where fv.data <= current_date and fv.is_venda_valida and fv.cliente_id is not null
group by 1, 2, 3, 4, 5, 6;

create index idx_mv_ai_cliente_data_loja on analytics.mv_ai_cliente_diario (data, loja_id);
create index idx_mv_ai_cliente_loja on analytics.mv_ai_cliente_diario (loja_id);
create index idx_mv_ai_cliente_cliente on analytics.mv_ai_cliente_diario (cliente_id);
create index idx_mv_ai_cliente_cnpj on analytics.mv_ai_cliente_diario (cnpj);

create materialized view analytics.mv_ai_produto_mensal as
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

create index idx_mv_ai_produto_mensal_mes_loja on analytics.mv_ai_produto_mensal (mes, loja_id);
create index idx_mv_ai_produto_mensal_loja on analytics.mv_ai_produto_mensal (loja_id);
create index idx_mv_ai_produto_mensal_produto on analytics.mv_ai_produto_mensal (produto_id);
create index idx_mv_ai_produto_mensal_receita on analytics.mv_ai_produto_mensal (receita_liquida_item);
create index idx_mv_ai_produto_mensal_lucro on analytics.mv_ai_produto_mensal (lucro_bruto_estimado);

create materialized view analytics.mv_ai_sazonalidade_dia_semana as
select
  f.data,
  f.associado_id,
  f.loja_id,
  regexp_replace(coalesce(l.cnpj, ''), '\D', '', 'g') as cnpj,
  extract(isodow from f.data)::int as dia_semana,
  case extract(isodow from f.data)::int
    when 1 then 'segunda-feira'
    when 2 then 'terca-feira'
    when 3 then 'quarta-feira'
    when 4 then 'quinta-feira'
    when 5 then 'sexta-feira'
    when 6 then 'sabado'
    else 'domingo'
  end as nome_dia_semana,
  f.qtd_cupons,
  f.faturamento_liquido,
  case when f.qtd_cupons = 0 then 0 else f.faturamento_liquido / f.qtd_cupons end as ticket_medio,
  f.valor_devolucao
from analytics.mv_kpi_faturamento_diario f
left join analytics.dim_loja l on l.loja_id = f.loja_id
where f.data <= current_date;

create index idx_mv_ai_sazonalidade_data_loja on analytics.mv_ai_sazonalidade_dia_semana (data, loja_id);
create index idx_mv_ai_sazonalidade_loja on analytics.mv_ai_sazonalidade_dia_semana (loja_id);
create index idx_mv_ai_sazonalidade_dia_semana on analytics.mv_ai_sazonalidade_dia_semana (dia_semana);
create index idx_mv_ai_sazonalidade_cnpj on analytics.mv_ai_sazonalidade_dia_semana (cnpj);

create materialized view analytics.mv_ai_desconto_devolucao_diario as
select
  o.data,
  o.associado_id,
  o.loja_id,
  regexp_replace(coalesce(l.cnpj, ''), '\D', '', 'g') as cnpj,
  o.total_cupons as qtd_cupons,
  coalesce(f.faturamento_liquido, 0) as faturamento_liquido,
  coalesce(o.desconto_manual, 0) as desconto_manual,
  coalesce(o.desconto_automatico, 0) as desconto_automatico,
  coalesce(o.desconto_total, 0) as desconto_total,
  case
    when coalesce(f.faturamento_liquido, 0) = 0 then null
    else coalesce(o.desconto_total, 0) / f.faturamento_liquido
  end as percentual_desconto,
  coalesce(f.valor_devolucao, 0) as valor_devolucao,
  case
    when coalesce(f.faturamento_liquido, 0) + coalesce(f.valor_devolucao, 0) = 0 then null
    else coalesce(f.valor_devolucao, 0) / (coalesce(f.faturamento_liquido, 0) + coalesce(f.valor_devolucao, 0))
  end as percentual_devolucao
from analytics.mv_kpi_operacional_diario o
left join analytics.mv_kpi_faturamento_diario f on f.data = o.data and f.associado_id = o.associado_id and f.loja_id = o.loja_id
left join analytics.dim_loja l on l.loja_id = o.loja_id
where o.data <= current_date;

create index idx_mv_ai_desc_dev_diario_data_loja on analytics.mv_ai_desconto_devolucao_diario (data, loja_id);
create index idx_mv_ai_desc_dev_diario_loja on analytics.mv_ai_desconto_devolucao_diario (loja_id);
create index idx_mv_ai_desc_dev_diario_cnpj on analytics.mv_ai_desconto_devolucao_diario (cnpj);

create materialized view analytics.mv_ai_desconto_devolucao_produto_mensal as
select
  date_trunc('month', fv.data)::date as mes,
  fvi.associado_id,
  fvi.loja_id,
  regexp_replace(coalesce(l.cnpj, ''), '\D', '', 'g') as cnpj,
  fvi.produto_id,
  max(fvi.nome_produto) as produto,
  sum(fvi.qtd_liquida) as qtd_liquida,
  sum(fvi.venda_liquida_item) as receita_liquida_item,
  sum(coalesce(fvi.vlr_desc_usu, 0)) as desconto_manual,
  sum(coalesce(fvi.vlr_desc_sist, 0)) as desconto_automatico,
  sum(coalesce(fvi.vlr_desc_usu, 0) + coalesce(fvi.vlr_desc_sist, 0)) as desconto_total,
  sum(coalesce(fvi.vlr_devol, 0)) as valor_devolucao,
  sum(coalesce(fvi.qtd_devol, 0)) as qtd_devolvida
from analytics.fact_venda_item fvi
join analytics.fact_venda fv on fv.venda_id = fvi.venda_id
left join analytics.dim_loja l on l.loja_id = fvi.loja_id
where fv.data <= current_date and fv.is_venda_valida
group by 1, 2, 3, 4, 5;

create index idx_mv_ai_desc_dev_produto_mes_loja on analytics.mv_ai_desconto_devolucao_produto_mensal (mes, loja_id);
create index idx_mv_ai_desc_dev_produto_loja on analytics.mv_ai_desconto_devolucao_produto_mensal (loja_id);
create index idx_mv_ai_desc_dev_produto_produto on analytics.mv_ai_desconto_devolucao_produto_mensal (produto_id);
create index idx_mv_ai_desc_dev_produto_devolucao on analytics.mv_ai_desconto_devolucao_produto_mensal (valor_devolucao);
create index idx_mv_ai_desc_dev_produto_desconto on analytics.mv_ai_desconto_devolucao_produto_mensal (desconto_total);

analyze analytics.mv_ai_resumo_executivo_diario;
analyze analytics.mv_ai_vendedor_diario;
analyze analytics.mv_ai_vendas_horario;
analyze analytics.mv_ai_alertas_operacionais;
analyze analytics.mv_ai_cliente_diario;
analyze analytics.mv_ai_produto_mensal;
analyze analytics.mv_ai_sazonalidade_dia_semana;
analyze analytics.mv_ai_desconto_devolucao_diario;
analyze analytics.mv_ai_desconto_devolucao_produto_mensal;
