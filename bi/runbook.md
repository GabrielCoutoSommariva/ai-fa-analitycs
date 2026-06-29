# Runbook BI

## Executar Scripts

```powershell
& "$env:USERPROFILE\scoop\apps\postgresql17\current\bin\psql.exe" -U postgres -d vendas -f "C:\Banco\bi\sql\00_profile_core.sql"
& "$env:USERPROFILE\scoop\apps\postgresql17\current\bin\psql.exe" -U postgres -d vendas -f "C:\Banco\bi\sql\01_analytics_schema.sql"
& "$env:USERPROFILE\scoop\apps\postgresql17\current\bin\psql.exe" -U postgres -d vendas -f "C:\Banco\bi\sql\02_kpi_views.sql"
& "$env:USERPROFILE\scoop\apps\postgresql17\current\bin\psql.exe" -U postgres -d vendas -f "C:\Banco\bi\sql\03_semantic_catalog.sql"
& "$env:USERPROFILE\scoop\apps\postgresql17\current\bin\psql.exe" -U postgres -d vendas -f "C:\Banco\bi\sql\99_smoke_tests.sql"
```

## Perguntas Que A IA Deve Conseguir Roteiar

- Quanto vendi hoje?
- Quanto vendi no mes?
- Qual foi o ticket medio?
- Quantos cupons foram emitidos?
- Quantos itens foram vendidos?
- Qual loja vendeu mais?
- Qual foi a margem bruta?
- Quais produtos deram mais lucro?
- Quais produtos venderam com prejuizo?
