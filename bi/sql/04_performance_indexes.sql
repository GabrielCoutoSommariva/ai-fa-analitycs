-- Indices de apoio para os dashboards BI.
-- Nao alteram dados; aceleram filtros por periodo/loja e joins de itens por venda.

create index if not exists idx_bi_vendas_cab_data
on vendas.vendas_cab (data);

create index if not exists idx_bi_vendas_cab_data_loja
on vendas.vendas_cab (data, id_loja);

create index if not exists idx_bi_vendas_item_id_venda
on vendas.vendas_item (id_venda);

create index if not exists idx_bi_vendas_item_loja
on vendas.vendas_item (id_loja);

create index if not exists idx_bi_vendas_item_venda_calc
on vendas.vendas_item (id_venda)
include (qtd_venda, qtd_devol, vlr_venda, vlr_devol, custo_real, custo_medio, custo_ult);

analyze vendas.vendas_cab;
analyze vendas.vendas_item;
