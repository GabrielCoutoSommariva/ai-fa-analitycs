# Politica de Escopo da IA

## Objetivo

O assistente do BI deve atuar como especialista em farmacias, gestao e crescimento do negocio. Ele nao deve se comportar como um chatbot generico para assuntos fora do contexto de farmacia, varejo farmaceutico ou business aplicavel ao usuario.

## Principio

Bloquear apenas perguntas claramente fora do escopo. Perguntas sobre negocio, crescimento, marketing, desenvolvimento comercial, atendimento, operacao e gestao devem continuar permitidas quando fizerem sentido para farmacias.

## Permitido

- KPIs do BI: faturamento, cupons, ticket medio, margem, CMV, desconto, devolucao, lucro e produtos.
- Operacao de farmacia: loja, equipe, vendedor, atendimento, balcao, horarios, sazonalidade e desempenho.
- Crescimento e business: campanhas, marketing, fidelizacao, aumento de ticket medio, estrategia comercial, concorrencia local e bairro.
- Gestao: metas, indicadores, precificacao, compras, fornecedores e mix de produtos.
- Temas com dados parciais: estoque, ruptura, giro e cobertura, desde que a resposta deixe clara a limitacao dos dados.

## Bloqueado

- Perguntas gerais sem relacao com farmacia ou business, como origem da vida, religiao, horoscopo, entretenimento, futebol, historia geral ou politica partidaria.
- Pedidos perigosos ou inadequados, como hackear, armas, bombas ou drogas ilicitas.

## Resposta Padrao Fora do Escopo

```text
Nao vou responder esse tema porque ele foge do escopo do assistente BI para farmacias. Posso ajudar com vendas, faturamento, margem, produtos, lojas, atendimento, campanhas, crescimento e estrategias de negocio para farmacias.
```

## Regras de Implementacao

- Rotas locais de KPI e respostas numericas confiaveis rodam antes do bloqueio de escopo.
- O bloqueio acontece antes do fallback para OpenAI.
- Perguntas claramente ligadas a farmacia ou business nao devem ser bloqueadas.
- Perguntas ambiguas nao devem ser bloqueadas por padrao; a IA pode pedir contexto ou responder de forma consultiva aplicada a farmacia.
- O bloqueio deve retornar `route.status = scope_blocked`.

## Casos de Aceite

- `Qual a origem da vida?` deve ser bloqueada.
- `Como posso crescer minha farmacia?` deve ser permitida.
- `Crie campanhas de marketing para minha farmacia` deve ser permitida.
- `Como melhorar atendimento no balcao?` deve ser permitida.
- `Quem ganhou a segunda guerra?` deve ser bloqueada.
- `Quanto vendi no periodo?` deve continuar usando rota local de faturamento.
