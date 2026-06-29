# Farmacias Associadas BI

Aplicacao modular para BI e perguntas futuras com IA sobre o banco `vendas`.

## Estrutura

- `backend`: FastAPI, PostgreSQL e camada semantica da IA
- `frontend`: Next.js com dashboard inicial
- `../bi/sql`: scripts SQL da camada `analytics`

## Backend

Atalho:

```powershell
cd C:\Banco\app
.\start-backend.ps1
```

Manual:

```powershell
cd C:\Banco\app\backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:DATABASE_URL="postgresql://postgres@localhost:5432/vendas"
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

## Frontend

Atalho:

```powershell
cd C:\Banco\app
.\start-frontend.ps1
```

Manual:

```powershell
cd C:\Banco\app\frontend
npm install
$env:BACKEND_INTERNAL_URL="http://127.0.0.1:8000"
npm run dev
```

Abra:

```text
http://localhost:3000
```

## Docker Compose

Recomendado quando o PostgreSQL ja esta rodando no Windows na porta `5432`:

```powershell
cd C:\Banco\app
docker compose up --build
```

Servicos:

- frontend: `http://localhost:3000`
- backend: `http://localhost:8000`

O backend no Docker usa por padrao:

```text
postgresql://postgres@host.docker.internal:5432/db_farmacias_bi
```

O frontend acessa o backend por um proxy fixo do Next em `/api/*`.
No Docker, esse proxy aponta para `http://backend:8000`.
No desenvolvimento local, `start-frontend.ps1` usa `http://127.0.0.1:8000`.

## OpenAI

Crie ou edite `C:\Banco\app\.env`:

```env
DATABASE_URL=postgresql://postgres@localhost:5432/db_farmacias_bi
BACKEND_INTERNAL_URL=http://127.0.0.1:8000
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o-mini
```

Preencha `OPENAI_API_KEY` apenas no ambiente real, nunca no repositorio. Sem chave, o chat usa fallback local: escolhe template, executa SQL seguro e retorna dados, mas nao chama provedor externo.

## Endpoints Principais

- `GET /health`
- `GET /metrics/catalog`
- `GET /metrics/summary`
- `GET /metrics/faturamento-diario`
- `GET /metrics/faturamento-mensal`
- `GET /metrics/faturamento-loja`
- `GET /metrics/lucro-produto`
- `GET /metrics/produtos-prejuizo`
- `GET /ai/context`
- `POST /ai/question`

## Conexao Frontend -> Backend

O frontend chama o backend por proxy interno do Next:

```text
/api/* -> BACKEND_INTERNAL_URL/*
```

Padrao local:

```text
BACKEND_INTERNAL_URL=http://127.0.0.1:8000
```

Teste rapido:

```powershell
Invoke-RestMethod http://127.0.0.1:3000/api/health
```
