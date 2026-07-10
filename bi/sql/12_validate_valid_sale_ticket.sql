-- Validacao local da regra homologada de venda valida e ticket medio.
-- Usa bronze.vendas_cab para evitar dependencia do FDW durante auditorias operacionais.
-- Uso esperado no psql:
--   \set data_inicio '2026-06-01'
--   \set data_fim '2026-07-01'
--   \i bi/sql/12_validate_valid_sale_ticket.sql

\if :{?data_inicio}
\else
  \set data_inicio '2026-06-01'
\endif

\if :{?data_fim}
\else
  \set data_fim '2026-07-01'
\endif

\echo '01. Distribuicao de st_caixa na bronze.vendas_cab'
select
  coalesce(st_caixa, '<null>') as st_caixa,
  count(*) as vendas,
  sum(vlr_liquido) as vlr_liquido,
  sum(vlr_devolucao) as vlr_devolucao,
  sum(vlr_liquido - vlr_devolucao) as faturamento_liquido
from bronze.vendas_cab
where data >= :'data_inicio'::date
  and data < :'data_fim'::date
group by 1
order by vendas desc;

\echo '02. Bronze bruta x vendas validas PA/DP'
select
  count(*) as vendas_totais,
  count(*) filter (where st_caixa in ('PA', 'DP')) as vendas_validas,
  count(*) filter (where st_caixa = 'DV') as devolucoes_totais_dv,
  sum(vlr_liquido - vlr_devolucao) as faturamento_total_sem_filtro,
  sum(vlr_liquido - vlr_devolucao) filter (where st_caixa in ('PA', 'DP')) as faturamento_valido,
  case
    when count(*) filter (where st_caixa in ('PA', 'DP')) = 0 then null
    else sum(vlr_liquido - vlr_devolucao) filter (where st_caixa in ('PA', 'DP')) / count(*) filter (where st_caixa in ('PA', 'DP'))
  end as ticket_medio_valido
from bronze.vendas_cab
where data >= :'data_inicio'::date
  and data < :'data_fim'::date;

\echo '03. MV faturamento deve bater com bronze valida PA/DP'
with bronze_valid as (
  select
    count(*) as cupons,
    sum(vlr_liquido - vlr_devolucao) as faturamento,
    case when count(*) = 0 then null else sum(vlr_liquido - vlr_devolucao) / count(*) end as ticket_medio
  from bronze.vendas_cab
  where data >= :'data_inicio'::date
    and data < :'data_fim'::date
    and st_caixa in ('PA', 'DP')
), mv as (
  select
    sum(qtd_cupons) as cupons,
    sum(faturamento_liquido) as faturamento,
    case when sum(qtd_cupons) = 0 then null else sum(faturamento_liquido) / sum(qtd_cupons) end as ticket_medio
  from analytics.mv_kpi_faturamento_diario
  where data >= :'data_inicio'::date
    and data < :'data_fim'::date
)
select
  bronze_valid.cupons as bronze_cupons,
  mv.cupons as mv_cupons,
  bronze_valid.cupons - mv.cupons as diff_cupons,
  bronze_valid.faturamento as bronze_faturamento,
  mv.faturamento as mv_faturamento,
  bronze_valid.faturamento - mv.faturamento as diff_faturamento,
  bronze_valid.ticket_medio as bronze_ticket_medio,
  mv.ticket_medio as mv_ticket_medio,
  bronze_valid.ticket_medio - mv.ticket_medio as diff_ticket_medio
from bronze_valid cross join mv;

\echo '04. Amostra por loja para conciliacao com ERP'
with bronze_valid as (
  select
    id_loja as loja_id,
    count(*) as cupons,
    sum(vlr_liquido - vlr_devolucao) as faturamento,
    case when count(*) = 0 then null else sum(vlr_liquido - vlr_devolucao) / count(*) end as ticket_medio
  from bronze.vendas_cab
  where data >= :'data_inicio'::date
    and data < :'data_fim'::date
    and st_caixa in ('PA', 'DP')
  group by id_loja
), mv as (
  select
    loja_id,
    sum(qtd_cupons) as cupons,
    sum(faturamento_liquido) as faturamento,
    case when sum(qtd_cupons) = 0 then null else sum(faturamento_liquido) / sum(qtd_cupons) end as ticket_medio
  from analytics.mv_kpi_faturamento_diario
  where data >= :'data_inicio'::date
    and data < :'data_fim'::date
  group by loja_id
)
select
  b.loja_id,
  l.nome as loja,
  b.cupons as bronze_cupons,
  m.cupons as mv_cupons,
  b.faturamento as bronze_faturamento,
  m.faturamento as mv_faturamento,
  b.ticket_medio as bronze_ticket_medio,
  m.ticket_medio as mv_ticket_medio
from bronze_valid b
join mv m on m.loja_id = b.loja_id
left join analytics.dim_loja l on l.loja_id = b.loja_id
order by b.faturamento desc
limit 10;
