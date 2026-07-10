-- Materializa dimensoes pequenas em tabelas locais para tirar o FDW do caminho quente.
-- Mantem as views analytics.dim_* como contrato estavel para backend, KPIs e IA.

create schema if not exists analytics;
create schema if not exists silver;

create table if not exists silver.dim_associado as
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
  software,
  now()::timestamptz as updated_at
from vendas.associado
with no data;

create table if not exists silver.dim_loja as
select
  id as loja_id,
  id_associado as associado_id,
  id_loja_interno,
  nome,
  cnpj,
  regexp_replace(coalesce(cnpj, ''), '\D', '', 'g') as cnpj_digits,
  now()::timestamptz as updated_at
from vendas.loja
with no data;

create table if not exists silver.dim_cliente as
select
  id as cliente_id,
  id_associado as associado_id,
  id_cliente_interno,
  nome,
  now()::timestamptz as updated_at
from vendas.cliente
with no data;

create table if not exists silver.dim_colaborador as
select
  id as colaborador_id,
  id_associado as associado_id,
  id_colaborador_interno,
  nome,
  now()::timestamptz as updated_at
from vendas.colaborador
with no data;

create table if not exists silver.dim_produto as
select
  id as produto_id,
  id_associado as associado_id,
  id_produto_interno,
  nome,
  gtin,
  preco_bruto,
  preco_liquido,
  custo_ult_entrada,
  now()::timestamptz as updated_at
from vendas.produto
with no data;

create unique index if not exists idx_silver_dim_associado_pk
on silver.dim_associado (associado_id);

create unique index if not exists idx_silver_dim_loja_pk
on silver.dim_loja (loja_id);

create unique index if not exists idx_silver_dim_cliente_pk
on silver.dim_cliente (cliente_id);

create unique index if not exists idx_silver_dim_colaborador_pk
on silver.dim_colaborador (colaborador_id);

create unique index if not exists idx_silver_dim_produto_pk
on silver.dim_produto (produto_id);

create index if not exists idx_silver_dim_associado_cnpj
on silver.dim_associado (cnpj);

create index if not exists idx_silver_dim_loja_associado
on silver.dim_loja (associado_id);

create index if not exists idx_silver_dim_loja_cnpj_digits
on silver.dim_loja (cnpj_digits);

create index if not exists idx_silver_dim_cliente_associado
on silver.dim_cliente (associado_id);

create index if not exists idx_silver_dim_colaborador_associado
on silver.dim_colaborador (associado_id);

create index if not exists idx_silver_dim_produto_associado
on silver.dim_produto (associado_id);

create index if not exists idx_silver_dim_produto_gtin
on silver.dim_produto (gtin);

drop function if exists analytics.refresh_local_dimensions();

create or replace function analytics.refresh_local_dimensions(include_large boolean default true)
returns void
language plpgsql
as $$
begin
  insert into silver.dim_associado (
    associado_id,
    id_associado_interno,
    nome,
    cnpj,
    status,
    data_inc,
    matriz,
    regiao,
    porte,
    software,
    updated_at
  )
  select
    id,
    id_associado_interno,
    nome,
    cnpj,
    status,
    data_inc,
    matriz,
    regiao,
    porte,
    software,
    now()
  from vendas.associado
  on conflict (associado_id) do update set
    id_associado_interno = excluded.id_associado_interno,
    nome = excluded.nome,
    cnpj = excluded.cnpj,
    status = excluded.status,
    data_inc = excluded.data_inc,
    matriz = excluded.matriz,
    regiao = excluded.regiao,
    porte = excluded.porte,
    software = excluded.software,
    updated_at = now();

  insert into silver.dim_loja (
    loja_id,
    associado_id,
    id_loja_interno,
    nome,
    cnpj,
    cnpj_digits,
    updated_at
  )
  select
    id,
    id_associado,
    id_loja_interno,
    nome,
    cnpj,
    regexp_replace(coalesce(cnpj, ''), '\D', '', 'g'),
    now()
  from vendas.loja
  on conflict (loja_id) do update set
    associado_id = excluded.associado_id,
    id_loja_interno = excluded.id_loja_interno,
    nome = excluded.nome,
    cnpj = excluded.cnpj,
    cnpj_digits = excluded.cnpj_digits,
    updated_at = now();

  insert into silver.dim_colaborador (
    colaborador_id,
    associado_id,
    id_colaborador_interno,
    nome,
    updated_at
  )
  select
    id,
    id_associado,
    id_colaborador_interno,
    nome,
    now()
  from vendas.colaborador
  on conflict (colaborador_id) do update set
    associado_id = excluded.associado_id,
    id_colaborador_interno = excluded.id_colaborador_interno,
    nome = excluded.nome,
    updated_at = now();

  if include_large then
    insert into silver.dim_cliente (
      cliente_id,
      associado_id,
      id_cliente_interno,
      nome,
      updated_at
    )
    select
      id,
      id_associado,
      id_cliente_interno,
      nome,
      now()
    from vendas.cliente
    on conflict (cliente_id) do update set
      associado_id = excluded.associado_id,
      id_cliente_interno = excluded.id_cliente_interno,
      nome = excluded.nome,
      updated_at = now();

    insert into silver.dim_produto (
      produto_id,
      associado_id,
      id_produto_interno,
      nome,
      gtin,
      preco_bruto,
      preco_liquido,
      custo_ult_entrada,
      updated_at
    )
    select
      id,
      id_associado,
      id_produto_interno,
      nome,
      gtin,
      preco_bruto,
      preco_liquido,
      custo_ult_entrada,
      now()
    from vendas.produto
    on conflict (produto_id) do update set
      associado_id = excluded.associado_id,
      id_produto_interno = excluded.id_produto_interno,
      nome = excluded.nome,
      gtin = excluded.gtin,
      preco_bruto = excluded.preco_bruto,
      preco_liquido = excluded.preco_liquido,
      custo_ult_entrada = excluded.custo_ult_entrada,
      updated_at = now();
  end if;

  delete from silver.dim_associado d
  where not exists (select 1 from vendas.associado s where s.id = d.associado_id);

  delete from silver.dim_loja d
  where not exists (select 1 from vendas.loja s where s.id = d.loja_id);

  delete from silver.dim_colaborador d
  where not exists (select 1 from vendas.colaborador s where s.id = d.colaborador_id);

  if include_large then
    delete from silver.dim_cliente d
    where not exists (select 1 from vendas.cliente s where s.id = d.cliente_id);

    delete from silver.dim_produto d
    where not exists (select 1 from vendas.produto s where s.id = d.produto_id);
  end if;

  analyze silver.dim_associado;
  analyze silver.dim_loja;
  analyze silver.dim_colaborador;
  if include_large then
    analyze silver.dim_cliente;
    analyze silver.dim_produto;
  end if;
end;
$$;

select analytics.refresh_local_dimensions();

create or replace view analytics.dim_associado as
select
  associado_id,
  id_associado_interno,
  nome,
  cnpj,
  status,
  data_inc,
  matriz,
  regiao,
  porte,
  software
from silver.dim_associado;

create or replace view analytics.dim_loja as
select
  loja_id,
  associado_id,
  id_loja_interno,
  nome,
  cnpj
from silver.dim_loja;

create or replace view analytics.dim_cliente as
select
  cliente_id,
  associado_id,
  id_cliente_interno,
  nome
from silver.dim_cliente;

create or replace view analytics.dim_colaborador as
select
  colaborador_id,
  associado_id,
  id_colaborador_interno,
  nome
from silver.dim_colaborador;

create or replace view analytics.dim_produto as
select
  produto_id,
  associado_id,
  id_produto_interno,
  nome,
  gtin,
  preco_bruto,
  preco_liquido,
  custo_ult_entrada
from silver.dim_produto;
