export type DateFilters = {
  dataInicio: string
  dataFim: string
  cnpj: string
}

export type LojaCnpj = {
  cnpj: string
  cnpj_digits: string
  lojas: number | string
  lojas_vinculadas: Array<{ loja_id: number; loja: string }>
}

export type SessionStore = {
  nomeFantasia: string
  cnpj: string
  acode: string
}

export type SessionUser = {
  id: string
  name: string
  email: string
  username: string
  type: string
  stores: SessionStore[]
  allowed_cnpjs: string[]
}

export type AuthState = {
  auth_enabled: boolean
  authenticated: boolean
  login_url?: string | null
  user?: SessionUser | null
}

export type SalesPeriod = {
  data_inicio: string | null
  data_fim: string | null
}

export type Summary = {
  faturamento: number | string
  faturamento_medio_loja?: number | string
  lojas_com_faturamento?: number | string
  cupons: number | string
  ticket_medio: number | string
  itens: number | string
  receita?: number | string
  custo?: number | string
  lucro: number | string
  margem: number | string | null
  matriz?: Omit<Summary, "matriz">
}

export type OperationalSummary = {
  total_cupons: number | string
  cupons_um_item: number | string
  percentual_cupons_um_item: number | string | null
  desconto_manual: number | string
  desconto_automatico: number | string
  desconto_total: number | string
  receita_liquida_item: number | string
  custo_total_estimado: number | string
  percentual_desconto_manual: number | string | null
  percentual_desconto_automatico: number | string | null
  percentual_desconto_total: number | string | null
  percentual_desconto_cmv: number | string | null
  cmv_percentual: number | string | null
  linhas_servico: number | string
  cupons_com_servico: number | string
  valor_servico: number | string
  desconto_servico: number | string
  custo_servico: number | string
}

export type DailyRevenue = {
  data: string
  associado_id: number
  loja_id: number
  qtd_cupons: number | string
  faturamento_liquido: number | string
  faturamento_produto: number | string
  faturamento_servico: number | string
  valor_devolucao: number | string
}

export type RevenueTrendPoint = {
  periodo: string
  label: string
  granularidade: "dia" | "mes" | "ano"
  qtd_cupons: number | string
  faturamento_liquido: number | string
}

export type MonthlyRevenue = {
  mes: string
  associado_id: number
  loja_id: number
  qtd_cupons: number | string
  faturamento_liquido: number | string
  faturamento_produto: number | string
  faturamento_servico: number | string
  valor_devolucao: number | string
}

export type CouponRow = {
  data: string
  associado_id: number
  loja_id: number
  qtd_cupons: number | string
  nro_venda_distintos: number | string
  tickets_distintos: number | string
}

export type ItemsSoldRow = {
  data: string
  associado_id: number
  loja_id: number
  linhas_item: number | string
  cupons_com_item: number | string
  qtd_itens_vendidos: number | string
  itens_por_cupom: number | string
}

export type StoreRevenue = {
  loja_id: number
  loja: string
  cnpj?: string | null
  qtd_cupons: number | string
  faturamento_liquido: number | string
}

export type ProductProfit = {
  produto_id: number
  produto: string
  qtd_vendida: number | string
  receita_liquida_item: number | string
  custo_total_estimado: number | string
  lucro_bruto_estimado: number | string
  margem_bruta_percentual?: number | string | null
}

export type AiRoute = {
  status: string
  question: string
  thread_id?: string | null
  answer?: string
  openai_enabled?: boolean
  rows?: Record<string, unknown>[]
  kpi_context?: Record<string, unknown>
  sql?: string
  params?: Record<string, unknown>
  route?: {
    status: string
    mode?: string
    intent?: string
    template?: {
      template_key: string
      metric_key: string
      question_pattern: string
      required_slots: string[]
      sql_template: string
      answer_guidance: string
    }
  }
  template?: {
    template_key: string
    metric_key: string
    question_pattern: string
    required_slots: string[]
    sql_template: string
    answer_guidance: string
  }
  safe_sql_template?: boolean
  message?: string
}

export type AiHistoryMessage = {
  role: "user" | "assistant"
  content: string
}

export type ProblemReportPayload = {
  title: string
  description: string
  category: string
  severity: string
  contact_email?: string | null
  page_url?: string | null
  filters?: Record<string, string>
  attachment_name?: string | null
  attachment_type?: string | null
  attachment_content?: string | null
}

export type ProblemReportResponse = {
  status: string
  message: string
}
