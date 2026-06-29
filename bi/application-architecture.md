# Arquitetura Da Aplicacao BI + IA

## Stack

- Backend: FastAPI
- Frontend: Next.js
- Banco: PostgreSQL
- Camada BI: schema `analytics`
- Camada IA: catalogo semantico em `analytics.ai_*`

## Modulos Backend

- `database`: conexao PostgreSQL
- `metrics`: leitura das views `analytics.kpi_*`
- `semantic`: leitura de `analytics.ai_context_export`
- `questions`: futuro roteamento de perguntas para OpenAI
- `sql_guard`: validacao de SQL gerado antes de executar

## Endpoints Iniciais

- `GET /health`
- `GET /metrics/catalog`
- `GET /metrics/faturamento-diario`
- `GET /metrics/faturamento-mensal`
- `GET /metrics/ticket-medio`
- `GET /metrics/cupons`
- `GET /metrics/itens-vendidos`
- `GET /metrics/faturamento-loja`
- `GET /metrics/lucro-produto`
- `GET /metrics/produtos-prejuizo`
- `GET /ai/context`
- `POST /ai/question`

## Fluxo Futuro Da IA

1. Usuario pergunta em linguagem natural.
2. Backend busca contexto em `analytics.ai_context_export`.
3. IA escolhe metrica/template.
4. Backend valida SQL permitido.
5. Backend executa somente SQL de leitura.
6. IA devolve resposta com valor, periodo, fonte e ressalvas.

## Regras De Seguranca Para IA

- Executar apenas `select`.
- Permitir apenas schema `analytics` para perguntas comuns.
- Bloquear `insert`, `update`, `delete`, `drop`, `alter`, `copy`, `create`.
- Sempre devolver fonte da metrica usada.
- Para lucro/margem, informar que e estimado ate homologacao de custo.

## Primeira Tela Do BI

- cards: faturamento diario, faturamento mensal, ticket medio, cupons, itens vendidos
- grafico: faturamento por dia
- ranking: faturamento por loja
- tabela: produtos com lucro/prejuizo estimado
- painel IA: pergunta em linguagem natural
