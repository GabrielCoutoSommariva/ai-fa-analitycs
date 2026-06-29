-- Catalogo semantico para IA: ensina origem, significado, joins e metricas.

create schema if not exists analytics;

create table if not exists analytics.ai_table_context (
  table_name text primary key,
  business_domain text not null,
  business_purpose text not null,
  grain text not null,
  primary_date_field text,
  critical_fields text[] not null default '{}',
  sensitive_fields text[] not null default '{}',
  notes text
);

create table if not exists analytics.ai_metric_catalog (
  metric_key text primary key,
  metric_name text not null,
  business_question text not null,
  source_view text not null,
  date_field text,
  value_field text,
  default_filters text,
  calculation text not null,
  caveats text
);

create table if not exists analytics.ai_join_graph (
  join_key text primary key,
  left_table text not null,
  right_table text not null,
  join_condition text not null,
  relationship_type text not null,
  business_meaning text not null
);

create table if not exists analytics.ai_business_terms (
  term_key text primary key,
  term_name text not null,
  definition text not null,
  preferred_source text not null,
  example_questions text[] not null default '{}'
);

create table if not exists analytics.ai_query_templates (
  template_key text primary key,
  metric_key text not null references analytics.ai_metric_catalog(metric_key),
  question_pattern text not null,
  required_slots text[] not null default '{}',
  sql_template text not null,
  answer_guidance text not null
);

insert into analytics.ai_table_context values
('vendas.vendas_cab', 'vendas', 'Cabecalho do cupom/venda PDV. Responde perguntas de faturamento, cupons, loja, cliente, caixa, status e datas.', '1 linha por venda/cupom', 'data', array['id','id_associado','id_loja','id_cliente','nro_venda','ticket','data','status','st_caixa','vlr_liquido','vlr_produto','vlr_servico','vlr_devolucao'], array['cpf_nf','obs_venda','obs_caixa'], 'Status valido ainda precisa ser confirmado por perfilamento.'),
('vendas.vendas_item', 'vendas', 'Itens vendidos dentro de cada cupom. Responde perguntas de quantidade, produto, margem, lucro, devolucao e vendedor.', '1 linha por item de venda', null, array['id','id_venda','id_produto','qtd_venda','qtd_devol','vlr_venda','vlr_unitario','custo_real','custo_medio','custo_ult','vlr_devol'], array[]::text[], 'Usar join com vendas_cab para data e status.'),
('vendas.produto', 'cadastro', 'Cadastro mestre de produtos com preco, GTIN e custo de ultima entrada.', '1 linha por produto', null, array['id','id_associado','nome','gtin','preco_bruto','preco_liquido','custo_ult_entrada'], array[]::text[], 'Nao possui categoria/fabricante no dump atual.'),
('vendas.loja', 'cadastro', 'Cadastro de lojas/filiais. Permite faturamento e lucro por unidade operacional.', '1 linha por loja', null, array['id','id_associado','nome','cnpj'], array['cnpj'], null),
('vendas.cliente', 'cadastro', 'Cadastro simples de clientes ligados ao associado.', '1 linha por cliente', null, array['id','id_associado','nome'], array[]::text[], 'Dados de cliente sao limitados neste dump.'),
('vendas.associado', 'tenant', 'Empresa/matriz/associado que organiza o contexto multiempresa do banco.', '1 linha por associado', 'data_inc', array['id','nome','cnpj','status','matriz','regiao','porte'], array['cnpj','email','cpf_prop','senha','serie'], null),
('vendas.nf_entrada_cab', 'compras', 'Cabecalho de nota fiscal de entrada. Responde perguntas de compras, fornecedores, impostos e custo fiscal.', '1 linha por nota de entrada', 'data_doc', array['id','id_associado','id_loja','id_fornecedor','data_doc','vlr_total','vlr_produto','stat_custo'], array['chave','arq_xml'], null),
('vendas.nf_entrada_item', 'compras', 'Itens da nota de entrada. Fonte alternativa para custo de compra por produto.', '1 linha por item de nota de entrada', null, array['id','id_nfiscal','id_produto','quantid','vlr_unitario','vlr_total','mov_estoq'], array[]::text[], 'Usar com nf_entrada_cab para data e fornecedor.')
on conflict (table_name) do update set
  business_domain = excluded.business_domain,
  business_purpose = excluded.business_purpose,
  grain = excluded.grain,
  primary_date_field = excluded.primary_date_field,
  critical_fields = excluded.critical_fields,
  sensitive_fields = excluded.sensitive_fields,
  notes = excluded.notes;

insert into analytics.ai_join_graph values
('venda_loja', 'vendas.vendas_cab', 'vendas.loja', 'vendas.vendas_cab.id_loja = vendas.loja.id', 'N:1', 'Cada venda pertence a uma loja.'),
('venda_cliente', 'vendas.vendas_cab', 'vendas.cliente', 'vendas.vendas_cab.id_cliente = vendas.cliente.id', 'N:1', 'Cada venda pode estar vinculada a um cliente.'),
('venda_associado', 'vendas.vendas_cab', 'vendas.associado', 'vendas.vendas_cab.id_associado = vendas.associado.id', 'N:1', 'Cada venda pertence a um associado/tenant.'),
('venda_item', 'vendas.vendas_item', 'vendas.vendas_cab', 'vendas.vendas_item.id_venda = vendas.vendas_cab.id', 'N:1', 'Itens detalham a composicao da venda.'),
('item_produto', 'vendas.vendas_item', 'vendas.produto', 'vendas.vendas_item.id_produto = vendas.produto.id', 'N:1', 'Cada item vendido referencia um produto.'),
('compra_item_nf', 'vendas.nf_entrada_item', 'vendas.nf_entrada_cab', 'vendas.nf_entrada_item.id_nfiscal = vendas.nf_entrada_cab.id', 'N:1', 'Itens detalham a nota de entrada.'),
('compra_item_produto', 'vendas.nf_entrada_item', 'vendas.produto', 'vendas.nf_entrada_item.id_produto = vendas.produto.id', 'N:1', 'Compra alimenta custo historico do produto.')
on conflict (join_key) do update set
  left_table = excluded.left_table,
  right_table = excluded.right_table,
  join_condition = excluded.join_condition,
  relationship_type = excluded.relationship_type,
  business_meaning = excluded.business_meaning;

insert into analytics.ai_metric_catalog values
('faturamento_diario', 'Faturamento diario', 'Quanto vendi em um dia?', 'analytics.kpi_faturamento_diario', 'data', 'faturamento_liquido', 'Usa valor ajustado por devolucao.', 'sum(vendas_cab.vlr_liquido - vendas_cab.vlr_devolucao) agrupado por data, associado e loja.', 'Status de venda valida ainda pode ser refinado por st_caixa/status.'),
('faturamento_mensal', 'Faturamento mensal', 'Quanto vendi no mes?', 'analytics.kpi_faturamento_mensal', 'mes', 'faturamento_liquido', 'Usa valor ajustado por devolucao.', 'sum(vendas_cab.vlr_liquido - vendas_cab.vlr_devolucao) agrupado por mes, associado e loja.', 'Status de venda valida ainda pode ser refinado por st_caixa/status.'),
('ticket_medio', 'Ticket medio', 'Qual o valor medio por cupom?', 'analytics.kpi_ticket_medio', 'data', 'ticket_medio', 'Usa valor ajustado por devolucao.', 'sum(vlr_liquido_ajustado) / count(cupons).', 'Cupom foi validado como vendas_cab.id; ticket possui poucos valores distintos.'),
('quantidade_cupons', 'Quantidade de cupons', 'Quantos cupons foram emitidos?', 'analytics.kpi_cupons', 'data', 'qtd_cupons', 'Status de venda valida pendente de confirmacao.', 'count(*) em vendas_cab.', 'Confirmar tratamento de cancelados/estornos.'),
('itens_por_cupom', 'Itens por cupom', 'Quantos itens em media cada cupom tem?', 'analytics.kpi_itens_vendidos', 'data', 'itens_por_cupom', 'Status de venda valida pendente de confirmacao.', 'sum(qtd_venda - qtd_devol) / count(distinct id_venda).', 'Depende de join vendas_item -> vendas_cab.'),
('itens_vendidos', 'Quantidade de itens vendidos', 'Quantos itens foram vendidos?', 'analytics.kpi_itens_vendidos', 'data', 'qtd_itens_vendidos', 'Status de venda valida pendente de confirmacao.', 'sum(qtd_venda - qtd_devol).', 'Confirmar devolucoes.'),
('faturamento_loja', 'Faturamento por loja', 'Quanto cada loja vendeu?', 'analytics.kpi_faturamento_loja', 'data', 'faturamento_liquido', 'Usa valor ajustado por devolucao.', 'sum(vlr_liquido_ajustado) agrupado por loja.', 'Usa dim_loja para nome da filial.'),
('margem_bruta', 'Margem bruta percentual', 'Qual a margem bruta?', 'analytics.kpi_lucro_total_diario', 'data', 'margem_bruta_percentual', 'Custo base pendente de confirmacao.', 'lucro_bruto_total / receita_liquida_item.', 'Custo usa prioridade custo_real, custo_medio, custo_ult, custo_ult_entrada.'),
('lucro_bruto_total', 'Lucro bruto total', 'Qual foi o lucro bruto?', 'analytics.kpi_lucro_total_diario', 'data', 'lucro_bruto_total', 'Custo base pendente de confirmacao.', 'sum(receita_liquida_item - custo_total_estimado).', 'Nao inclui despesas operacionais.'),
('lucro_produto', 'Lucro por produto', 'Quais produtos deram mais lucro?', 'analytics.kpi_lucro_produto', 'data', 'lucro_bruto_estimado', 'Custo base pendente de confirmacao.', 'sum(venda_liquida_item - custo_total_base) por produto.', 'Estimado ate validar custo oficial.'),
('produtos_prejuizo', 'Produtos vendidos com prejuizo', 'Quais produtos venderam abaixo do custo?', 'analytics.kpi_produtos_prejuizo', 'data', 'lucro_bruto_estimado', 'Custo base pendente de confirmacao.', 'produtos com lucro_bruto_estimado < 0.', 'Pode refletir desconto, devolucao, subsidio ou custo incorreto.')
on conflict (metric_key) do update set
  metric_name = excluded.metric_name,
  business_question = excluded.business_question,
  source_view = excluded.source_view,
  date_field = excluded.date_field,
  value_field = excluded.value_field,
  default_filters = excluded.default_filters,
  calculation = excluded.calculation,
  caveats = excluded.caveats;

insert into analytics.ai_business_terms values
('cupom', 'Cupom', 'Unidade de venda no PDV. Inicialmente representada por vendas_cab.id.', 'vendas.vendas_cab', array['quantos cupons foram emitidos?', 'qual ticket medio por cupom?']),
('faturamento', 'Faturamento', 'Valor vendido no PDV, ajustado por devolucoes. Usa vendas_cab.vlr_liquido - vendas_cab.vlr_devolucao.', 'analytics.fact_venda', array['quanto vendi hoje?', 'qual faturamento mensal?', 'quanto a loja vendeu?']),
('item_vendido', 'Item vendido', 'Produto vendido dentro de um cupom. Usa vendas_item e quantidade liquida.', 'vendas.vendas_item', array['quantos itens vendi?', 'quais produtos venderam mais?']),
('lucro_bruto', 'Lucro bruto', 'Receita liquida do item menos custo estimado. Nao inclui despesas operacionais.', 'analytics.kpi_lucro_produto', array['qual lucro por produto?', 'quais produtos deram prejuizo?']),
('loja', 'Loja', 'Filial/unidade operacional onde a venda ocorreu.', 'vendas.loja', array['quanto vendeu por loja?', 'qual loja vendeu mais?'])
on conflict (term_key) do update set
  term_name = excluded.term_name,
  definition = excluded.definition,
  preferred_source = excluded.preferred_source,
  example_questions = excluded.example_questions;

insert into analytics.ai_query_templates values
('tpl_faturamento_dia', 'faturamento_diario', 'quanto vendi em <data>?', array['data'], 'select data, sum(faturamento_liquido) as faturamento from analytics.kpi_faturamento_diario where data = :data group by data;', 'Responder como faturamento liquido ajustado por devolucoes.'),
('tpl_faturamento_mes', 'faturamento_mensal', 'quanto vendi no mes <mes>?', array['mes'], 'select mes, sum(faturamento_liquido) as faturamento from analytics.kpi_faturamento_mensal where mes = date_trunc(''month'', :data::date)::date group by mes;', 'Responder como faturamento mensal liquido ajustado por devolucoes.'),
('tpl_ticket_medio', 'ticket_medio', 'qual foi o ticket medio em <periodo>?', array['data_inicio','data_fim'], 'select sum(faturamento_liquido) / nullif(sum(qtd_cupons), 0) as ticket_medio from analytics.kpi_ticket_medio where data between :data_inicio and :data_fim;', 'Explicar que ticket medio e faturamento dividido por quantidade de cupons.'),
('tpl_cupons', 'quantidade_cupons', 'quantos cupons foram emitidos em <periodo>?', array['data_inicio','data_fim'], 'select sum(qtd_cupons) as qtd_cupons from analytics.kpi_cupons where data between :data_inicio and :data_fim;', 'Usar vendas_cab.id como cupom.'),
('tpl_itens_vendidos', 'itens_vendidos', 'quantos itens foram vendidos em <periodo>?', array['data_inicio','data_fim'], 'select sum(qtd_itens_vendidos) as itens_vendidos from analytics.kpi_itens_vendidos where data between :data_inicio and :data_fim;', 'Quantidade liquida: qtd_venda menos qtd_devol.'),
('tpl_margem_bruta', 'margem_bruta', 'qual foi a margem em <periodo>?', array['data_inicio','data_fim'], 'select sum(receita_liquida_item) as receita, sum(custo_total_estimado) as custo, sum(lucro_bruto_total) as lucro_bruto_total, case when sum(receita_liquida_item) = 0 then null else sum(lucro_bruto_total) / sum(receita_liquida_item) end as margem_bruta_percentual from analytics.kpi_lucro_total_diario where data between :data_inicio and :data_fim;', 'Margem bruta estimada com base no custo disponivel nos itens de venda.'),
('tpl_faturamento_loja', 'faturamento_loja', 'quanto cada loja vendeu em <periodo>?', array['data_inicio','data_fim'], 'select loja, sum(faturamento_liquido) as faturamento from analytics.kpi_faturamento_loja where data between :data_inicio and :data_fim group by loja order by faturamento desc;', 'Rankear lojas por faturamento liquido.'),
('tpl_lucro_produto', 'lucro_produto', 'quais produtos deram mais lucro em <periodo>?', array['data_inicio','data_fim'], 'select produto, sum(receita_liquida_item) as receita, sum(custo_total_estimado) as custo, sum(lucro_bruto_estimado) as lucro from analytics.kpi_lucro_produto where data between :data_inicio and :data_fim group by produto order by lucro desc limit 20;', 'Informar que lucro e estimado ate validacao final de custo.'),
('tpl_produtos_prejuizo', 'produtos_prejuizo', 'quais produtos venderam com prejuizo em <periodo>?', array['data_inicio','data_fim'], 'select produto, sum(receita_liquida_item) as receita, sum(custo_total_estimado) as custo, sum(lucro_bruto_estimado) as prejuizo from analytics.kpi_lucro_produto where data between :data_inicio and :data_fim group by produto having sum(lucro_bruto_estimado) < 0 order by prejuizo asc limit 20;', 'Explicar que prejuizo pode indicar desconto, custo errado, fracionamento ou devolucao.')
on conflict (template_key) do update set
  metric_key = excluded.metric_key,
  question_pattern = excluded.question_pattern,
  required_slots = excluded.required_slots,
  sql_template = excluded.sql_template,
  answer_guidance = excluded.answer_guidance;

create or replace view analytics.ai_context_export as
select
  'metric' as context_type,
  metric_key as context_key,
  jsonb_build_object(
    'metric_name', metric_name,
    'business_question', business_question,
    'source_view', source_view,
    'date_field', date_field,
    'value_field', value_field,
    'default_filters', default_filters,
    'calculation', calculation,
    'caveats', caveats
  ) as context_payload
from analytics.ai_metric_catalog
union all
select
  'table' as context_type,
  table_name as context_key,
  jsonb_build_object(
    'business_domain', business_domain,
    'business_purpose', business_purpose,
    'grain', grain,
    'primary_date_field', primary_date_field,
    'critical_fields', critical_fields,
    'sensitive_fields', sensitive_fields,
    'notes', notes
  ) as context_payload
from analytics.ai_table_context
union all
select
  'join' as context_type,
  join_key as context_key,
  jsonb_build_object(
    'left_table', left_table,
    'right_table', right_table,
    'join_condition', join_condition,
    'relationship_type', relationship_type,
    'business_meaning', business_meaning
  ) as context_payload
from analytics.ai_join_graph
union all
select
  'template' as context_type,
  template_key as context_key,
  jsonb_build_object(
    'metric_key', metric_key,
    'question_pattern', question_pattern,
    'required_slots', required_slots,
    'sql_template', sql_template,
    'answer_guidance', answer_guidance
  ) as context_payload
from analytics.ai_query_templates;
