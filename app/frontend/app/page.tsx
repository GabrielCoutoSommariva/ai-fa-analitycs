"use client"

import type { ColumnDef } from "@tanstack/react-table"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { AlertTriangle } from "lucide-react"
import { useEffect, useState } from "react"

import { AiChat } from "@/components/AiChat"
import { AppShell, type DashboardSection } from "@/components/AppShell"
import { ChartPanel } from "@/components/ChartPanel"
import { DataTable } from "@/components/DataTable"
import { DrillDownPanel } from "@/components/DrillDownPanel"
import { FilterBar } from "@/components/FilterBar"
import { KpiCard } from "@/components/KpiCard"
import { ProblemReportButton } from "@/components/ProblemReportButton"
import { ItemsPerCouponChart, MarginHero, ProductProfitChart, RevenueTrendChart, StoreRankingChart, StoreScatterChart } from "@/components/charts"
import { api } from "@/lib/api"
import { compactMoney, compactNumber, money, number, percent } from "@/lib/format"
import type { AuthState, CouponRow, DailyRevenue, DateFilters, ItemsSoldRow, MonthlyRevenue, ProductProfit, StoreRevenue } from "@/lib/types"

type TrendGranularity = "auto" | "dia" | "mes" | "ano"

const defaultFilters: DateFilters = {
  dataInicio: "",
  dataFim: "",
  cnpj: ""
}

function formatInputDate(value: Date) {
  const year = value.getFullYear()
  const month = String(value.getMonth() + 1).padStart(2, "0")
  const day = String(value.getDate()).padStart(2, "0")
  return `${year}-${month}-${day}`
}

function browserDefaultFilters(): DateFilters {
  const today = new Date()
  return {
    ...defaultFilters,
    dataInicio: previousMonthStartFromDate(formatInputDate(today)),
    dataFim: formatInputDate(today)
  }
}

function previousMonthStartFromDate(value: string | null | undefined) {
  if (!value || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return ""
  const year = Number(value.slice(0, 4))
  const month = Number(value.slice(5, 7))
  const previousYear = month === 1 ? year - 1 : year
  const previousMonth = month === 1 ? 12 : month - 1
  return `${previousYear}-${String(previousMonth).padStart(2, "0")}-01`
}

export default function Home() {
  const [filters, setFilters] = useState(browserDefaultFilters)
  const [activeSection, setActiveSection] = useState<DashboardSection>("overview")
  const [authState, setAuthState] = useState<AuthState | null>(null)
  const [authChecked, setAuthChecked] = useState(false)
  const [authError, setAuthError] = useState<string | null>(null)
  const [dateDefaultsApplied, setDateDefaultsApplied] = useState(false)
  const [trendGranularity, setTrendGranularity] = useState<TrendGranularity>("auto")
  const queryClient = useQueryClient()
  const isOverview = activeSection === "overview"
  const isSales = activeSection === "sales"
  const isStores = activeSection === "stores"
  const isProducts = activeSection === "products"
  const isMargin = activeSection === "margin"
  const canLoadPeriod = authChecked && !authError
  const canLoadMetrics = canLoadPeriod && Boolean(filters.dataInicio && filters.dataFim)

  const salesPeriod = useQuery({ queryKey: ["salesPeriod"], queryFn: api.salesPeriod, enabled: canLoadPeriod })

  useEffect(() => {
    let cancelled = false

    async function initializeSession() {
      try {
        const url = new URL(window.location.href)
        const token = url.searchParams.get("token")
        const session = token ? await api.createSession(token) : await api.me()

        if (cancelled) return
        if (token) {
          url.searchParams.delete("token")
          window.history.replaceState({}, "", `${url.pathname}${url.search}${url.hash}`)
        }

        if (session.auth_enabled && !session.authenticated) {
          if (session.login_url) {
            window.location.href = session.login_url
            return
          }
          setAuthError("Sessão inválida ou expirada.")
        }
        setAuthState(session)
      } catch {
        try {
          const session = await api.me()
          if (!cancelled && session.auth_enabled && session.login_url) {
            window.location.href = session.login_url
            return
          }
        } catch {
          // Keep the local error below if the auth service itself is unavailable.
        }
        if (!cancelled) setAuthError("Não foi possível validar o acesso.")
      } finally {
        if (!cancelled) setAuthChecked(true)
      }
    }

    initializeSession()
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    if (!authState?.user?.allowed_cnpjs.length || !filters.cnpj) return
    const selected = filters.cnpj.replace(/\D/g, "")
    if (selected && !authState.user.allowed_cnpjs.includes(selected)) {
      setFilters({ ...filters, cnpj: "" })
    }
  }, [authState, filters])

  useEffect(() => {
    const lastLoadedDate = salesPeriod.data?.data_fim
    if (dateDefaultsApplied || !lastLoadedDate) return

    setFilters((current) => {
      return { ...current, dataInicio: previousMonthStartFromDate(lastLoadedDate), dataFim: lastLoadedDate }
    })
    setDateDefaultsApplied(true)
  }, [dateDefaultsApplied, salesPeriod.data?.data_fim])

  const summary = useQuery({ queryKey: ["summary", filters], queryFn: () => api.summary(filters), enabled: canLoadMetrics })
  const matrixSummary = useQuery({ queryKey: ["matrixSummary", filters.dataInicio, filters.dataFim], queryFn: () => api.matrixSummary(filters), enabled: canLoadMetrics && summary.isSuccess })
  const operational = useQuery({ queryKey: ["operationalSummary", filters], queryFn: () => api.operationalSummary(filters), enabled: canLoadMetrics })
  const operationalMatrix = useQuery({ queryKey: ["operationalMatrixSummary", filters.dataInicio, filters.dataFim], queryFn: () => api.operationalMatrixSummary(filters), enabled: canLoadMetrics && operational.isSuccess })
  const trend = useQuery({ queryKey: ["revenueTrend", filters, trendGranularity], queryFn: () => api.revenueTrend(filters, trendGranularity), enabled: canLoadMetrics && (isOverview || isSales) })
  const daily = useQuery({ queryKey: ["dailyRevenue", filters], queryFn: () => api.dailyRevenue(filters), enabled: canLoadMetrics && isSales })
  const monthly = useQuery({ queryKey: ["monthlyRevenue", filters], queryFn: () => api.monthlyRevenue(filters), enabled: canLoadMetrics && isSales })
  const coupons = useQuery({ queryKey: ["coupons", filters], queryFn: () => api.coupons(filters), enabled: canLoadMetrics && isSales })
  const itemsSold = useQuery({ queryKey: ["itemsSold", filters], queryFn: () => api.itemsSold(filters), enabled: canLoadMetrics && isSales })
  const stores = useQuery({ queryKey: ["storeRevenue", filters], queryFn: () => api.storeRevenue(filters), enabled: canLoadMetrics && (isOverview || isStores) })
  const mostProfitable = useQuery({ queryKey: ["productProfit", filters, "desc"], queryFn: () => api.productProfit(filters, "desc"), enabled: canLoadMetrics && (isProducts || isMargin) })
  const leastProfitable = useQuery({ queryKey: ["productProfit", filters, "asc"], queryFn: () => api.productProfit(filters, "asc"), enabled: canLoadMetrics && isMargin })
  const losses = useQuery({ queryKey: ["productLosses", filters], queryFn: () => api.productLosses(filters), enabled: canLoadMetrics && (isOverview || isProducts || isMargin) })

  const queries = [summary, operational, operationalMatrix, trend, daily, monthly, coupons, itemsSold, stores, mostProfitable, leastProfitable, losses]
  const isLoading = queries.some((query) => query.isFetching)
  const error = queries.find((query) => query.error)?.error
  const trendControls = (
    <div className="trend-controls" aria-label="Agrupamento do gráfico">
      {([
        ["auto", "Auto"],
        ["dia", "Dia"],
        ["mes", "Mês"],
        ["ano", "Ano"]
      ] as Array<[TrendGranularity, string]>).map(([value, label]) => (
        <button className={trendGranularity === value ? "active" : ""} key={value} type="button" onClick={() => setTrendGranularity(value)}>
          {label}
        </button>
      ))}
    </div>
  )

  if (!authChecked) {
    return <div className="status-screen">Validando acesso...</div>
  }

  if (authError) {
    return <div className="status-screen status-screen--error">{authError}</div>
  }

  if (salesPeriod.isError) {
    return <div className="status-screen status-screen--error">Não foi possível carregar o período atualizado do banco.</div>
  }

  const dailyColumns: ColumnDef<DailyRevenue>[] = [
    { accessorKey: "data", header: "Data" },
    { accessorKey: "loja_id", header: "Loja" },
    { accessorKey: "qtd_cupons", header: "Cupons", cell: ({ row }) => number(row.original.qtd_cupons, 0) },
    { accessorKey: "faturamento_liquido", header: "Faturamento", cell: ({ row }) => money(row.original.faturamento_liquido) },
    { accessorKey: "valor_devolucao", header: "Devolução", cell: ({ row }) => money(row.original.valor_devolucao) }
  ]

  const monthlyColumns: ColumnDef<MonthlyRevenue>[] = [
    { accessorKey: "mes", header: "Mês" },
    { accessorKey: "loja_id", header: "Loja" },
    { accessorKey: "qtd_cupons", header: "Cupons", cell: ({ row }) => number(row.original.qtd_cupons, 0) },
    { accessorKey: "faturamento_liquido", header: "Faturamento", cell: ({ row }) => money(row.original.faturamento_liquido) },
    { accessorKey: "faturamento_servico", header: "Serviços", cell: ({ row }) => money(row.original.faturamento_servico) }
  ]

  const couponColumns: ColumnDef<CouponRow>[] = [
    { accessorKey: "data", header: "Data" },
    { accessorKey: "loja_id", header: "Loja" },
    { accessorKey: "qtd_cupons", header: "Cupons", cell: ({ row }) => number(row.original.qtd_cupons, 0) },
    { accessorKey: "nro_venda_distintos", header: "Nºs de venda", cell: ({ row }) => number(row.original.nro_venda_distintos, 0) },
    { accessorKey: "tickets_distintos", header: "Tickets", cell: ({ row }) => number(row.original.tickets_distintos, 0) }
  ]

  const itemColumns: ColumnDef<ItemsSoldRow>[] = [
    { accessorKey: "data", header: "Data" },
    { accessorKey: "loja_id", header: "Loja" },
    { accessorKey: "linhas_item", header: "Linhas", cell: ({ row }) => number(row.original.linhas_item, 0) },
    { accessorKey: "qtd_itens_vendidos", header: "Itens vendidos", cell: ({ row }) => number(row.original.qtd_itens_vendidos, 0) },
    { accessorKey: "itens_por_cupom", header: "Itens/cupom", cell: ({ row }) => number(row.original.itens_por_cupom) }
  ]

  const storeColumns: ColumnDef<StoreRevenue>[] = [
    { accessorKey: "loja", header: "Loja" },
    { accessorKey: "cnpj", header: "CNPJ" },
    { accessorKey: "loja_id", header: "ID" },
    { accessorKey: "qtd_cupons", header: "Cupons", cell: ({ row }) => number(row.original.qtd_cupons, 0) },
    { accessorKey: "faturamento_liquido", header: "Faturamento", cell: ({ row }) => money(row.original.faturamento_liquido) }
  ]

  const productColumns: ColumnDef<ProductProfit>[] = [
    { accessorKey: "produto", header: "Produto" },
    { accessorKey: "produto_id", header: "ID" },
    { accessorKey: "qtd_vendida", header: "Qtd", cell: ({ row }) => number(row.original.qtd_vendida) },
    { accessorKey: "receita_liquida_item", header: "Receita", cell: ({ row }) => money(row.original.receita_liquida_item) },
    { accessorKey: "custo_total_estimado", header: "CMV", cell: ({ row }) => money(row.original.custo_total_estimado) },
    { accessorKey: "lucro_bruto_estimado", header: "Lucro", cell: ({ row }) => <span className={Number(row.original.lucro_bruto_estimado) < 0 ? "danger" : "success"}>{money(row.original.lucro_bruto_estimado)}</span> },
    { accessorKey: "margem_bruta_percentual", header: "Margem", cell: ({ row }) => row.original.margem_bruta_percentual == null ? "-" : percent(row.original.margem_bruta_percentual) }
  ]

  const overview = (
    <div className="visual-grid">
      <ChartPanel title="Faturamento e cupons" subtitle="Evolução por dia, mês ou ano conforme o intervalo" actions={trendControls} isLoading={trend.isFetching}>
        <RevenueTrendChart data={trend.data ?? []} />
      </ChartPanel>
      <ChartPanel title="Faturamento por loja" subtitle="Todas as lojas no período" isLoading={stores.isFetching}>
        <StoreRankingChart data={stores.data ?? []} />
      </ChartPanel>
      <ChartPanel title="Produtos em prejuízo" subtitle="Maiores perdas estimadas" badge="estimado" isLoading={losses.isFetching}>
        <ProductProfitChart data={losses.data ?? []} mode="loss" />
      </ChartPanel>
      <ChartPanel title="Margem bruta" subtitle="Receita PDV, CMV estimado e lucro bruto" badge="estimada" isLoading={summary.isFetching}>
        <MarginHero summary={summary.data} />
      </ChartPanel>
    </div>
  )

  const sales = (
    <div className="stack">
      <div className="visual-grid visual-grid--wide">
        <ChartPanel title="Faturamento" subtitle="Linha de faturamento e barras de cupons" actions={trendControls} isLoading={trend.isFetching}>
          <RevenueTrendChart data={trend.data ?? []} />
        </ChartPanel>
        <ChartPanel title="Itens por cupom" subtitle="Qualidade do cupom médio no período" isLoading={itemsSold.isFetching}>
          <ItemsPerCouponChart data={itemsSold.data ?? []} />
        </ChartPanel>
      </div>
      <DrillDownPanel title="Ver dados de vendas" subtitle="Faturamento diário, mensal, cupons e itens">
        <div className="stack">
          <DataTable title="Faturamento diário" source="analytics.kpi_faturamento_diario" columns={dailyColumns} data={daily.data ?? []} isLoading={daily.isFetching} />
          <DataTable title="Faturamento mensal" source="analytics.kpi_faturamento_mensal" columns={monthlyColumns} data={monthly.data ?? []} isLoading={monthly.isFetching} />
          <DataTable title="Cupons emitidos" source="analytics.kpi_cupons" columns={couponColumns} data={coupons.data ?? []} isLoading={coupons.isFetching} />
          <DataTable title="Itens vendidos" source="analytics.kpi_itens_vendidos" columns={itemColumns} data={itemsSold.data ?? []} isLoading={itemsSold.isFetching} />
        </div>
      </DrillDownPanel>
    </div>
  )

  const storesSection = (
    <div className="stack">
      <div className="visual-grid visual-grid--wide">
        <ChartPanel title="Faturamento por loja" subtitle="Todas as lojas no período" isLoading={stores.isFetching}>
          <StoreRankingChart data={stores.data ?? []} />
        </ChartPanel>
        <ChartPanel title="Cupons x ticket" subtitle="Dispersão operacional por loja" isLoading={stores.isFetching}>
          <StoreScatterChart data={stores.data ?? []} />
        </ChartPanel>
      </div>
      <DrillDownPanel title="Ver tabela de lojas" subtitle="Ranking completo e valores consolidados">
        <DataTable title="Faturamento por loja" source="analytics.kpi_faturamento_loja" columns={storeColumns} data={stores.data ?? []} isLoading={stores.isFetching} />
      </DrillDownPanel>
    </div>
  )

  const products = (
    <div className="stack">
      <div className="visual-grid visual-grid--wide">
        <ChartPanel title="Produtos mais lucrativos" subtitle="Top produtos por lucro bruto estimado" badge="estimado" isLoading={mostProfitable.isFetching}>
          <ProductProfitChart data={mostProfitable.data ?? []} />
        </ChartPanel>
        <ChartPanel title="Produtos com prejuízo" subtitle="Itens com lucro bruto negativo" badge="risco" isLoading={losses.isFetching}>
          <ProductProfitChart data={losses.data ?? []} mode="loss" />
        </ChartPanel>
      </div>
      <DrillDownPanel title="Ver produtos em detalhe" subtitle="Lucro, CMV, receita e margem por produto">
        <div className="stack">
          <DataTable title="Produtos mais lucrativos" source="analytics.kpi_lucro_produto" columns={productColumns} data={mostProfitable.data ?? []} isLoading={mostProfitable.isFetching} />
          <DataTable title="Produtos vendidos com prejuízo" source="analytics.kpi_produtos_prejuizo" columns={productColumns} data={losses.data ?? []} isLoading={losses.isFetching} />
        </div>
      </DrillDownPanel>
    </div>
  )

  const margin = (
    <div className="stack">
      <ChartPanel title="Margem bruta" subtitle="Receita PDV, CMV estimado e lucro bruto" badge="homologar CMV" isLoading={summary.isFetching}>
        <MarginHero summary={summary.data} />
      </ChartPanel>
      <div className="visual-grid visual-grid--wide">
        <ChartPanel title="Mais lucrativos" subtitle="Produtos que mais contribuem no lucro" isLoading={mostProfitable.isFetching}>
          <ProductProfitChart data={mostProfitable.data ?? []} />
        </ChartPanel>
        <ChartPanel title="Menos lucrativos" subtitle="Produtos com pior resultado estimado" badge="atenção" isLoading={leastProfitable.isFetching}>
          <ProductProfitChart data={leastProfitable.data ?? []} mode="loss" />
        </ChartPanel>
      </div>
      <DrillDownPanel title="Ver dados técnicos de margem" subtitle="Tabelas usadas para auditoria do cálculo">
        <div className="stack">
          <DataTable title="Produtos menos lucrativos" source="analytics.kpi_lucro_produto" columns={productColumns} data={leastProfitable.data ?? []} isLoading={leastProfitable.isFetching} />
          <DataTable title="Produtos com prejuízo" source="analytics.kpi_produtos_prejuizo" columns={productColumns} data={losses.data ?? []} isLoading={losses.isFetching} />
        </div>
      </DrillDownPanel>
    </div>
  )

  const sections: Record<DashboardSection, React.ReactNode> = {
    overview,
    sales,
    stores: storesSection,
    products,
    margin
  }
  const matrix = matrixSummary.data
  const operationalData = operational.data
  const operationalMatrixData = operationalMatrix.data

  return (
    <AppShell activeSection={activeSection} onSectionChange={setActiveSection}>
      <main>
        <header className="page-header">
          <div>
            <h1>Inteligência da Farmácia</h1>
            <p>KPIs operacionais, tabelas modernas e contexto semântico para perguntas com IA.</p>
          </div>
        </header>

        <FilterBar filters={filters} setFilters={setFilters} isLoading={isLoading || salesPeriod.isFetching} onRefresh={() => queryClient.invalidateQueries()} authorizedStores={authState?.user?.stores} />
        {error && <div className="error-banner"><AlertTriangle size={16} /> {error instanceof Error ? error.message : "Erro ao carregar dados"}</div>}

        <section className="kpi-grid">
          <KpiCard label="Faturamento líquido" value={compactMoney(summary.data?.faturamento)} baseline={matrix ? compactMoney(matrix.faturamento_medio_loja ?? matrix.faturamento) : undefined} baselineLabel="Média rede" />
          <KpiCard label="Cupons" value={compactNumber(summary.data?.cupons, 0)} baseline={matrix ? compactNumber(matrix.cupons, 0) : undefined} />
          <KpiCard label="Ticket médio" value={money(summary.data?.ticket_medio)} baseline={matrix ? money(matrix.ticket_medio) : undefined} />
          <KpiCard label="Itens vendidos" value={compactNumber(summary.data?.itens, 0)} baseline={matrix ? compactNumber(matrix.itens, 0) : undefined} />
          <KpiCard label="Lucro bruto" value={compactMoney(summary.data?.lucro)} baseline={matrix ? compactMoney(matrix.lucro) : undefined} />
          <KpiCard label="Margem" value={percent(summary.data?.margem)} baseline={matrix ? percent(matrix.margem) : undefined} />
          <KpiCard label="Desconto usuário" value={percent(operationalData?.percentual_desconto_manual)} baseline={operationalData ? compactMoney(operationalData.desconto_manual) : undefined} baselineLabel="Valor" secondaryBaseline={operationalMatrixData ? percent(operationalMatrixData.percentual_desconto_manual) : undefined} secondaryBaselineLabel="Rede" />
          <KpiCard label="Desconto automático" value={percent(operationalData?.percentual_desconto_automatico)} baseline={operationalData ? compactMoney(operationalData.desconto_automatico) : undefined} baselineLabel="Valor" secondaryBaseline={operationalMatrixData ? percent(operationalMatrixData.percentual_desconto_automatico) : undefined} secondaryBaselineLabel="Rede" />
          <KpiCard label="Desconto / CMV" value={percent(operationalData?.percentual_desconto_cmv)} baseline={operationalData ? compactMoney(operationalData.custo_total_estimado) : undefined} baselineLabel="CMV" secondaryBaseline={operationalMatrixData ? percent(operationalMatrixData.percentual_desconto_cmv) : undefined} secondaryBaselineLabel="Rede" />
          <KpiCard label="Cupons 1 item" value={percent(operationalData?.percentual_cupons_um_item)} baseline={operationalData ? `${compactNumber(operationalData.cupons_um_item, 0)} de ${compactNumber(operationalData.total_cupons, 0)}` : undefined} baselineLabel="Cupons" secondaryBaseline={operationalMatrixData ? percent(operationalMatrixData.percentual_cupons_um_item) : undefined} secondaryBaselineLabel="Rede" />
        </section>

        {sections[activeSection]}
      </main>
      <ProblemReportButton filters={filters} user={authState?.user} />
      <AiChat filters={filters} />
    </AppShell>
  )
}
