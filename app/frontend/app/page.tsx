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
import { ItemsPerCouponChart, MarginHero, ProductProfitChart, RevenueTrendChart, StoreRankingChart, StoreScatterChart } from "@/components/charts"
import { api } from "@/lib/api"
import { compactMoney, compactNumber, money, number, percent } from "@/lib/format"
import type { AuthState, CouponRow, DailyRevenue, DateFilters, ItemsSoldRow, MonthlyRevenue, ProductProfit, StoreRevenue } from "@/lib/types"

const defaultFilters: DateFilters = {
  dataInicio: "2026-05-01",
  dataFim: "2026-05-12",
  cnpj: ""
}

export default function Home() {
  const [filters, setFilters] = useState(defaultFilters)
  const [activeSection, setActiveSection] = useState<DashboardSection>("overview")
  const [authState, setAuthState] = useState<AuthState | null>(null)
  const [authChecked, setAuthChecked] = useState(false)
  const [authError, setAuthError] = useState<string | null>(null)
  const queryClient = useQueryClient()
  const isOverview = activeSection === "overview"
  const isSales = activeSection === "sales"
  const isStores = activeSection === "stores"
  const isProducts = activeSection === "products"
  const isMargin = activeSection === "margin"
  const canLoadMetrics = authChecked && !authError

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
          setAuthError("Sessao invalida ou expirada.")
        }
        setAuthState(session)
      } catch {
        if (!cancelled) setAuthError("Nao foi possivel validar o acesso.")
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

  const summary = useQuery({ queryKey: ["summary", filters], queryFn: () => api.summary(filters), enabled: canLoadMetrics })
  const daily = useQuery({ queryKey: ["dailyRevenue", filters], queryFn: () => api.dailyRevenue(filters), enabled: canLoadMetrics && (isOverview || isSales) })
  const monthly = useQuery({ queryKey: ["monthlyRevenue", filters], queryFn: () => api.monthlyRevenue(filters), enabled: canLoadMetrics && isSales })
  const coupons = useQuery({ queryKey: ["coupons", filters], queryFn: () => api.coupons(filters), enabled: canLoadMetrics && isSales })
  const itemsSold = useQuery({ queryKey: ["itemsSold", filters], queryFn: () => api.itemsSold(filters), enabled: canLoadMetrics && isSales })
  const stores = useQuery({ queryKey: ["storeRevenue", filters], queryFn: () => api.storeRevenue(filters), enabled: canLoadMetrics && (isOverview || isStores) })
  const mostProfitable = useQuery({ queryKey: ["productProfit", filters, "desc"], queryFn: () => api.productProfit(filters, "desc"), enabled: canLoadMetrics && (isProducts || isMargin) })
  const leastProfitable = useQuery({ queryKey: ["productProfit", filters, "asc"], queryFn: () => api.productProfit(filters, "asc"), enabled: canLoadMetrics && isMargin })
  const losses = useQuery({ queryKey: ["productLosses", filters], queryFn: () => api.productLosses(filters), enabled: canLoadMetrics && (isOverview || isProducts || isMargin) })

  const queries = [summary, daily, monthly, coupons, itemsSold, stores, mostProfitable, leastProfitable, losses]
  const isLoading = queries.some((query) => query.isFetching)
  const error = queries.find((query) => query.error)?.error

  if (!authChecked) {
    return <div className="status-screen">Validando acesso...</div>
  }

  if (authError) {
    return <div className="status-screen status-screen--error">{authError}</div>
  }

  const dailyColumns: ColumnDef<DailyRevenue>[] = [
    { accessorKey: "data", header: "Data" },
    { accessorKey: "loja_id", header: "Loja" },
    { accessorKey: "qtd_cupons", header: "Cupons", cell: ({ row }) => number(row.original.qtd_cupons, 0) },
    { accessorKey: "faturamento_liquido", header: "Faturamento", cell: ({ row }) => money(row.original.faturamento_liquido) },
    { accessorKey: "valor_devolucao", header: "Devolucao", cell: ({ row }) => money(row.original.valor_devolucao) }
  ]

  const monthlyColumns: ColumnDef<MonthlyRevenue>[] = [
    { accessorKey: "mes", header: "Mes" },
    { accessorKey: "loja_id", header: "Loja" },
    { accessorKey: "qtd_cupons", header: "Cupons", cell: ({ row }) => number(row.original.qtd_cupons, 0) },
    { accessorKey: "faturamento_liquido", header: "Faturamento", cell: ({ row }) => money(row.original.faturamento_liquido) },
    { accessorKey: "faturamento_servico", header: "Servicos", cell: ({ row }) => money(row.original.faturamento_servico) }
  ]

  const couponColumns: ColumnDef<CouponRow>[] = [
    { accessorKey: "data", header: "Data" },
    { accessorKey: "loja_id", header: "Loja" },
    { accessorKey: "qtd_cupons", header: "Cupons", cell: ({ row }) => number(row.original.qtd_cupons, 0) },
    { accessorKey: "nro_venda_distintos", header: "Nros venda", cell: ({ row }) => number(row.original.nro_venda_distintos, 0) },
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
    { accessorKey: "custo_total_estimado", header: "Custo", cell: ({ row }) => money(row.original.custo_total_estimado) },
    { accessorKey: "lucro_bruto_estimado", header: "Lucro", cell: ({ row }) => <span className={Number(row.original.lucro_bruto_estimado) < 0 ? "danger" : "success"}>{money(row.original.lucro_bruto_estimado)}</span> },
    { accessorKey: "margem_bruta_percentual", header: "Margem", cell: ({ row }) => row.original.margem_bruta_percentual == null ? "-" : percent(row.original.margem_bruta_percentual) }
  ]

  const overview = (
    <div className="visual-grid">
      <ChartPanel title="Faturamento e cupons" subtitle="Evolucao diaria do periodo selecionado" isLoading={daily.isFetching}>
        <RevenueTrendChart data={daily.data ?? []} />
      </ChartPanel>
      <ChartPanel title="Faturamento por loja" subtitle="Todas as lojas no periodo" isLoading={stores.isFetching}>
        <StoreRankingChart data={stores.data ?? []} />
      </ChartPanel>
      <ChartPanel title="Produtos em prejuizo" subtitle="Maiores perdas estimadas" badge="estimado" isLoading={losses.isFetching}>
        <ProductProfitChart data={losses.data ?? []} mode="loss" />
      </ChartPanel>
      <ChartPanel title="Margem bruta" subtitle="Preco de compra + preco de venda + vendas PDV" badge="estimada" isLoading={summary.isFetching}>
        <MarginHero summary={summary.data} />
      </ChartPanel>
    </div>
  )

  const sales = (
    <div className="stack">
      <div className="visual-grid visual-grid--wide">
        <ChartPanel title="Faturamento diario" subtitle="Linha de faturamento e barras de cupons" isLoading={daily.isFetching}>
          <RevenueTrendChart data={daily.data ?? []} />
        </ChartPanel>
        <ChartPanel title="Itens por cupom" subtitle="Qualidade do cupom medio no periodo" isLoading={itemsSold.isFetching}>
          <ItemsPerCouponChart data={itemsSold.data ?? []} />
        </ChartPanel>
      </div>
      <DrillDownPanel title="Ver dados de vendas" subtitle="Faturamento diario, mensal, cupons e itens">
        <div className="stack">
          <DataTable title="Faturamento diario" source="analytics.kpi_faturamento_diario" columns={dailyColumns} data={daily.data ?? []} isLoading={daily.isFetching} />
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
        <ChartPanel title="Faturamento por loja" subtitle="Todas as lojas no periodo" isLoading={stores.isFetching}>
          <StoreRankingChart data={stores.data ?? []} />
        </ChartPanel>
        <ChartPanel title="Cupons x ticket" subtitle="Dispersao operacional por loja" isLoading={stores.isFetching}>
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
        <ChartPanel title="Produtos com prejuizo" subtitle="Itens com lucro bruto negativo" badge="risco" isLoading={losses.isFetching}>
          <ProductProfitChart data={losses.data ?? []} mode="loss" />
        </ChartPanel>
      </div>
      <DrillDownPanel title="Ver produtos em detalhe" subtitle="Lucro, custo, receita e margem por produto">
        <div className="stack">
          <DataTable title="Produtos mais lucrativos" source="analytics.kpi_lucro_produto" columns={productColumns} data={mostProfitable.data ?? []} isLoading={mostProfitable.isFetching} />
          <DataTable title="Produtos vendidos com prejuizo" source="analytics.kpi_produtos_prejuizo" columns={productColumns} data={losses.data ?? []} isLoading={losses.isFetching} />
        </div>
      </DrillDownPanel>
    </div>
  )

  const margin = (
    <div className="stack">
      <ChartPanel title="Margem bruta" subtitle="Preco de compra + preco de venda + vendas PDV" badge="homologar custo" isLoading={summary.isFetching}>
        <MarginHero summary={summary.data} />
      </ChartPanel>
      <div className="visual-grid visual-grid--wide">
        <ChartPanel title="Mais lucrativos" subtitle="Produtos que mais contribuem no lucro" isLoading={mostProfitable.isFetching}>
          <ProductProfitChart data={mostProfitable.data ?? []} />
        </ChartPanel>
        <ChartPanel title="Menos lucrativos" subtitle="Produtos com pior resultado estimado" badge="atencao" isLoading={leastProfitable.isFetching}>
          <ProductProfitChart data={leastProfitable.data ?? []} mode="loss" />
        </ChartPanel>
      </div>
      <DrillDownPanel title="Ver dados tecnicos de margem" subtitle="Tabelas usadas para auditoria do calculo">
        <div className="stack">
          <DataTable title="Produtos menos lucrativos" source="analytics.kpi_lucro_produto" columns={productColumns} data={leastProfitable.data ?? []} isLoading={leastProfitable.isFetching} />
          <DataTable title="Produtos com prejuizo" source="analytics.kpi_produtos_prejuizo" columns={productColumns} data={losses.data ?? []} isLoading={losses.isFetching} />
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

  return (
    <AppShell activeSection={activeSection} onSectionChange={setActiveSection}>
      <main>
        <header className="page-header">
          <div>
            <h1>Inteligencia da Farmacia</h1>
            <p>KPIs operacionais, tabelas modernas e contexto semantico para perguntas com IA.</p>
          </div>
        </header>

        <FilterBar filters={filters} setFilters={setFilters} isLoading={isLoading} onRefresh={() => queryClient.invalidateQueries()} authorizedStores={authState?.user?.stores} />
        {error && <div className="error-banner"><AlertTriangle size={16} /> {error instanceof Error ? error.message : "Erro ao carregar dados"}</div>}

        <section className="kpi-grid">
          <KpiCard label="Faturamento" value={compactMoney(summary.data?.faturamento)} note="ajustado" tone="success" />
          <KpiCard label="Cupons" value={compactNumber(summary.data?.cupons, 0)} />
          <KpiCard label="Ticket medio" value={money(summary.data?.ticket_medio)} />
          <KpiCard label="Itens vendidos" value={compactNumber(summary.data?.itens, 0)} />
          <KpiCard label="Lucro bruto" value={compactMoney(summary.data?.lucro)} note="estimado" tone="warning" />
          <KpiCard label="Margem" value={percent(summary.data?.margem)} note="estimada" tone="warning" />
        </section>

        {sections[activeSection]}
      </main>
      <AiChat filters={filters} />
    </AppShell>
  )
}
