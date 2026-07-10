-- Copia local das tabelas transacionais usadas pelo BI.
-- Esta camada ainda nao troca os fatos analytics.*; ela prepara a remocao do FDW do caminho quente.

create schema if not exists analytics;
create schema if not exists bronze;

create table if not exists bronze.vendas_cab as
select *
from vendas.vendas_cab
with no data;

create table if not exists bronze.vendas_item as
select *
from vendas.vendas_item
with no data;

create table if not exists bronze.vendas_serv as
select *
from vendas.vendas_serv
with no data;

create unique index if not exists idx_bronze_vendas_cab_id
on bronze.vendas_cab (id);

create index if not exists idx_bronze_vendas_cab_data
on bronze.vendas_cab (data);

create index if not exists idx_bronze_vendas_cab_data_loja
on bronze.vendas_cab (data, id_loja);

create index if not exists idx_bronze_vendas_cab_loja
on bronze.vendas_cab (id_loja);

create unique index if not exists idx_bronze_vendas_item_id
on bronze.vendas_item (id);

create index if not exists idx_bronze_vendas_item_id_venda
on bronze.vendas_item (id_venda);

create index if not exists idx_bronze_vendas_item_loja
on bronze.vendas_item (id_loja);

create index if not exists idx_bronze_vendas_item_produto
on bronze.vendas_item (id_produto);

create index if not exists idx_bronze_vendas_item_vendedor
on bronze.vendas_item (id_vendedor);

create unique index if not exists idx_bronze_vendas_serv_id
on bronze.vendas_serv (id);

create index if not exists idx_bronze_vendas_serv_id_venda
on bronze.vendas_serv (id_venda);

create index if not exists idx_bronze_vendas_serv_loja
on bronze.vendas_serv (id_loja);

create or replace function analytics.refresh_bronze_sales(p_days_back integer default 30)
returns table(table_name text, rows_loaded bigint)
language plpgsql
as $$
declare
  v_data_inicio date;
  v_data_fim date := current_date;
  v_cab_rows bigint := 0;
  v_item_rows bigint := 0;
  v_serv_rows bigint := 0;
begin
  if p_days_back is null or p_days_back < 0 then
    raise exception 'p_days_back must be a non-negative integer';
  end if;

  v_data_inicio := current_date - p_days_back;

  create temporary table tmp_bronze_venda_ids on commit drop as
  select distinct id as venda_id
  from vendas.vendas_cab
  where data between v_data_inicio and v_data_fim;

  create temporary table tmp_bronze_vendas_cab on commit drop as
  select distinct on (c.id) c.*
  from vendas.vendas_cab c
  join tmp_bronze_venda_ids v on v.venda_id = c.id
  order by c.id;

  create temporary table tmp_bronze_vendas_item on commit drop as
  select distinct on (i.id) i.*
  from vendas.vendas_item i
  join tmp_bronze_venda_ids v on v.venda_id = i.id_venda
  order by i.id;

  create temporary table tmp_bronze_vendas_serv on commit drop as
  select distinct on (s.id) s.*
  from vendas.vendas_serv s
  join tmp_bronze_venda_ids v on v.venda_id = s.id_venda
  order by s.id;

  delete from bronze.vendas_serv s
  using tmp_bronze_venda_ids v
  where s.id_venda = v.venda_id;

  delete from bronze.vendas_serv s
  using tmp_bronze_vendas_serv tmp
  where s.id = tmp.id;

  delete from bronze.vendas_item i
  using tmp_bronze_venda_ids v
  where i.id_venda = v.venda_id;

  delete from bronze.vendas_item i
  using tmp_bronze_vendas_item tmp
  where i.id = tmp.id;

  delete from bronze.vendas_cab c
  using tmp_bronze_venda_ids v
  where c.id = v.venda_id;

  insert into bronze.vendas_cab
  select *
  from tmp_bronze_vendas_cab;
  get diagnostics v_cab_rows = row_count;

  insert into bronze.vendas_item
  select *
  from tmp_bronze_vendas_item;
  get diagnostics v_item_rows = row_count;

  insert into bronze.vendas_serv
  select *
  from tmp_bronze_vendas_serv;
  get diagnostics v_serv_rows = row_count;

  analyze bronze.vendas_cab;
  analyze bronze.vendas_item;
  analyze bronze.vendas_serv;

  return query values
    ('bronze.vendas_cab'::text, v_cab_rows),
    ('bronze.vendas_item'::text, v_item_rows),
    ('bronze.vendas_serv'::text, v_serv_rows);
end;
$$;
