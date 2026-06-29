# Contexto Para IA

## Fonte Principal

Use a view abaixo para exportar o contexto semantico que sera enviado para a IA:

```sql
select * from analytics.ai_context_export order by context_type, context_key;
```

## Como A IA Deve Raciocinar

- Identificar a intencao da pergunta.
- Localizar a metrica em `analytics.ai_metric_catalog`.
- Usar um template de `analytics.ai_query_templates` quando existir.
- Validar joins em `analytics.ai_join_graph`.
- Explicar limitacoes usando `caveats` e `answer_guidance`.

## Regras De Resposta

- Responder com o valor calculado.
- Informar a metrica usada.
- Informar periodo/filtro aplicado.
- Quando for lucro/margem, dizer que e estimado enquanto custo nao for homologado.
- Quando houver devolucao, usar faturamento liquido ajustado.
