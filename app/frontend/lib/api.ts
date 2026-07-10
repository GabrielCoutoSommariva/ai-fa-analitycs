import type {
  AiRoute,
  AuthState,
  CouponRow,
  DailyRevenue,
  DateFilters,
  ItemsSoldRow,
  LojaCnpj,
  MonthlyRevenue,
  OperationalSummary,
  ProductProfit,
  ProblemReportPayload,
  ProblemReportResponse,
  RevenueTrendPoint,
  SalesPeriod,
  StoreRevenue,
  Summary,
  AiHistoryMessage
} from "./types"

const API_BASE = "/api"

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, { cache: "no-store", credentials: "same-origin" })
  if (!response.ok) throw new Error(`Erro ${response.status}`)
  return response.json()
}

function query(filters: DateFilters, extra: Record<string, string | number | undefined> = {}) {
  const params = new URLSearchParams()
  if (filters.dataInicio) params.set("data_inicio", filters.dataInicio)
  if (filters.dataFim) params.set("data_fim", filters.dataFim)
  if (filters.cnpj) params.set("cnpj", filters.cnpj)
  Object.entries(extra).forEach(([key, value]) => {
    if (value !== undefined && value !== "") params.set(key, String(value))
  })
  return params.toString()
}

export const api = {
  createSession: (token: string) => getJson<AuthState>(`/auth/session?token=${encodeURIComponent(token)}`),
  me: () => getJson<AuthState>("/auth/me"),
  logout: async () => {
    const response = await fetch(`${API_BASE}/auth/logout`, { method: "POST", credentials: "same-origin" })
    if (!response.ok) throw new Error(`Erro ${response.status}`)
    return response.json() as Promise<AuthState>
  },
  salesPeriod: () => getJson<SalesPeriod>("/metrics/periodo-vendas"),
  lojasCnpj: () => getJson<LojaCnpj[]>("/metrics/lojas-cnpj"),
  summary: (filters: DateFilters) => getJson<Summary>(`/metrics/summary?${query(filters)}`),
  matrixSummary: (filters: DateFilters) => getJson<Summary>(`/metrics/summary-matriz?${query({ ...filters, cnpj: "" })}`),
  operationalSummary: (filters: DateFilters) => getJson<OperationalSummary>(`/metrics/operacional-summary?${query(filters)}`),
  operationalMatrixSummary: (filters: DateFilters) => getJson<OperationalSummary>(`/metrics/operacional-summary-matriz?${query({ ...filters, cnpj: "" })}`),
  revenueTrend: (filters: DateFilters, granularidade: "auto" | "dia" | "mes" | "ano") => getJson<RevenueTrendPoint[]>(`/metrics/faturamento-tendencia?${query(filters, { granularidade })}`),
  dailyRevenue: (filters: DateFilters) => getJson<DailyRevenue[]>(`/metrics/faturamento-diario?${query(filters, { limit: 250 })}`),
  monthlyRevenue: (filters: DateFilters) => {
    const params = new URLSearchParams()
    if (filters.dataInicio) params.set("mes_inicio", filters.dataInicio)
    if (filters.dataFim) params.set("mes_fim", filters.dataFim)
    if (filters.cnpj) params.set("cnpj", filters.cnpj)
    params.set("limit", "250")
    return getJson<MonthlyRevenue[]>(`/metrics/faturamento-mensal?${params.toString()}`)
  },
  coupons: (filters: DateFilters) => getJson<CouponRow[]>(`/metrics/cupons?${query(filters, { limit: 250 })}`),
  itemsSold: (filters: DateFilters) => getJson<ItemsSoldRow[]>(`/metrics/itens-vendidos?${query(filters, { limit: 250 })}`),
  storeRevenue: (filters: DateFilters) => getJson<StoreRevenue[]>(`/metrics/faturamento-loja?${query(filters, { limit: 100 })}`),
  productProfit: (filters: DateFilters, order: "asc" | "desc") => getJson<ProductProfit[]>(`/metrics/lucro-produto?${query(filters, { order, limit: 100 })}`),
  productLosses: (filters: DateFilters) => getJson<ProductProfit[]>(`/metrics/produtos-prejuizo?${query(filters, { limit: 100 })}`),
  ask: async (question: string, filters: DateFilters, history: AiHistoryMessage[] = [], threadId?: string) => {
    const response = await fetch(`${API_BASE}/ai/question`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify({
        question,
        data_inicio: filters.dataInicio || null,
        data_fim: filters.dataFim || null,
        cnpj: filters.cnpj || null,
        history,
        thread_id: threadId || null
      })
    })
    if (!response.ok) throw new Error(`Erro ${response.status}`)
    return response.json() as Promise<AiRoute>
  },
  reportProblem: async (payload: ProblemReportPayload) => {
    const response = await fetch(`${API_BASE}/support/problem-report`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify(payload)
    })
    if (!response.ok) {
      const data = await response.json().catch(() => null)
      throw new Error(data?.detail ?? `Erro ${response.status}`)
    }
    return response.json() as Promise<ProblemReportResponse>
  }
}
