"use client"

import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ComposedChart,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis
} from "recharts"

import { money, number, percent } from "@/lib/format"
import type { DailyRevenue, ItemsSoldRow, ProductProfit, StoreRevenue, Summary } from "@/lib/types"

const colors = {
  accent: "#18b8a8",
  blue: "#0f9f92",
  warning: "#ff6a00",
  danger: "#d64040",
  muted: "#60717d",
  grid: "rgba(7,17,31,.08)"
}

const tooltipStyle = {
  background: "#ffffff",
  border: "1px solid rgba(7,17,31,.12)",
  borderRadius: 14,
  color: "#07111f"
}

function axisMoney(value: number) {
  if (Math.abs(value) >= 1_000_000) return `R$ ${(value / 1_000_000).toFixed(1)}M`
  if (Math.abs(value) >= 1_000) return `R$ ${(value / 1_000).toFixed(0)}k`
  return `R$ ${value}`
}

function shortLabel(value: string, max = 24) {
  return value.length > max ? `${value.slice(0, max - 1)}...` : value
}

export function RevenueTrendChart({ data }: { data: DailyRevenue[] }) {
  const grouped = Object.values(data.reduce<Record<string, { data: string; faturamento: number; cupons: number }>>((acc, row) => {
    const key = row.data
    acc[key] ??= { data: key, faturamento: 0, cupons: 0 }
    acc[key].faturamento += Number(row.faturamento_liquido ?? 0)
    acc[key].cupons += Number(row.qtd_cupons ?? 0)
    return acc
  }, {})).sort((a, b) => a.data.localeCompare(b.data))

  return (
    <ResponsiveContainer width="100%" height={320}>
      <ComposedChart data={grouped}>
        <CartesianGrid stroke={colors.grid} vertical={false} />
        <XAxis dataKey="data" tick={{ fill: colors.muted, fontSize: 12 }} tickMargin={12} />
        <YAxis yAxisId="left" tickFormatter={axisMoney} tick={{ fill: colors.muted, fontSize: 12 }} width={80} />
        <YAxis yAxisId="right" orientation="right" tickFormatter={(v) => number(v, 0)} tick={{ fill: colors.muted, fontSize: 12 }} width={60} />
        <Tooltip contentStyle={tooltipStyle} formatter={(value, name) => name === "faturamento" ? money(value as number) : number(value as number, 0)} />
        <Area yAxisId="left" type="monotone" dataKey="faturamento" fill="rgba(24,184,168,.18)" stroke={colors.accent} strokeWidth={3} />
        <Bar yAxisId="right" dataKey="cupons" fill="rgba(255,106,0,.58)" radius={[8, 8, 0, 0]} />
      </ComposedChart>
    </ResponsiveContainer>
  )
}

export function StoreRankingChart({ data }: { data: StoreRevenue[] }) {
  const chartData = data.map((row) => ({
    loja: row.loja,
    lojaLabel: shortLabel(`${row.loja} #${row.loja_id}`, 28),
    faturamento: Number(row.faturamento_liquido ?? 0),
    cupons: Number(row.qtd_cupons ?? 0)
  }))
  const height = Math.max(360, chartData.length * 34 + 46)
  return (
    <div className="chart-scroll">
      <div style={{ height }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={chartData} layout="vertical" margin={{ left: 8, right: 20 }}>
            <CartesianGrid stroke={colors.grid} horizontal={false} />
            <XAxis type="number" tickFormatter={axisMoney} tick={{ fill: colors.muted, fontSize: 12 }} />
            <YAxis type="category" dataKey="lojaLabel" width={170} tick={{ fill: colors.muted, fontSize: 11 }} />
            <Tooltip cursor={false} contentStyle={tooltipStyle} formatter={(value) => money(value as number)} labelFormatter={(_, payload) => payload?.[0]?.payload?.loja ?? ""} />
            <Bar dataKey="faturamento" fill={colors.blue} radius={[0, 10, 10, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}

export function StoreScatterChart({ data }: { data: StoreRevenue[] }) {
  const chartData = data.map((row) => ({ loja: row.loja, faturamento: Number(row.faturamento_liquido ?? 0), cupons: Number(row.qtd_cupons ?? 0), ticket: Number(row.faturamento_liquido ?? 0) / Math.max(Number(row.qtd_cupons ?? 0), 1) }))
  return (
    <ResponsiveContainer width="100%" height={320}>
      <ScatterChart>
        <CartesianGrid stroke={colors.grid} />
        <XAxis type="number" dataKey="cupons" name="Cupons" tick={{ fill: colors.muted, fontSize: 12 }} />
        <YAxis type="number" dataKey="ticket" name="Ticket" tickFormatter={(v) => `R$ ${Number(v).toFixed(0)}`} tick={{ fill: colors.muted, fontSize: 12 }} />
        <Tooltip cursor={{ strokeDasharray: "3 3" }} contentStyle={tooltipStyle} formatter={(value, name) => name === "Ticket" ? money(value as number) : number(value as number, 0)} />
        <Scatter data={chartData} fill={colors.accent} />
      </ScatterChart>
    </ResponsiveContainer>
  )
}

export function ProductProfitChart({ data, mode = "profit" }: { data: ProductProfit[]; mode?: "profit" | "loss" }) {
  const chartData = data.slice(0, 12).map((row) => ({ produto: row.produto, produtoLabel: shortLabel(row.produto, 26), lucro: Number(row.lucro_bruto_estimado ?? 0) }))
  return (
    <ResponsiveContainer width="100%" height={360}>
      <BarChart data={chartData} layout="vertical" margin={{ left: 8, right: 20 }}>
        <CartesianGrid stroke={colors.grid} horizontal={false} />
        <XAxis type="number" tickFormatter={axisMoney} tick={{ fill: colors.muted, fontSize: 12 }} />
        <YAxis type="category" dataKey="produtoLabel" width={160} tick={{ fill: colors.muted, fontSize: 11 }} />
        <Tooltip contentStyle={tooltipStyle} formatter={(value) => money(value as number)} labelFormatter={(_, payload) => payload?.[0]?.payload?.produto ?? ""} />
        <Bar dataKey="lucro" radius={[0, 10, 10, 0]}>
          {chartData.map((entry, index) => <Cell key={`${entry.produto}-${index}`} fill={mode === "loss" || entry.lucro < 0 ? colors.danger : colors.accent} />)}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}

export function ItemsPerCouponChart({ data }: { data: ItemsSoldRow[] }) {
  const grouped = Object.values(data.reduce<Record<string, { data: string; itensPorCupom: number }>>((acc, row) => {
    acc[row.data] = { data: row.data, itensPorCupom: Number(row.itens_por_cupom ?? 0) }
    return acc
  }, {})).sort((a, b) => a.data.localeCompare(b.data))

  return (
    <ResponsiveContainer width="100%" height={260}>
      <AreaChart data={grouped}>
        <CartesianGrid stroke={colors.grid} vertical={false} />
        <XAxis dataKey="data" tick={{ fill: colors.muted, fontSize: 12 }} />
        <YAxis tick={{ fill: colors.muted, fontSize: 12 }} />
        <Tooltip contentStyle={tooltipStyle} formatter={(value) => number(value as number)} />
        <Area type="monotone" dataKey="itensPorCupom" fill="rgba(255,106,0,.16)" stroke={colors.warning} strokeWidth={3} />
      </AreaChart>
    </ResponsiveContainer>
  )
}

export function MarginHero({ summary }: { summary?: Summary }) {
  const margem = Number(summary?.margem ?? 0)
  const lucro = Number(summary?.lucro ?? 0)
  const receita = Number(summary?.receita ?? summary?.faturamento ?? 0)
  const custo = Number(summary?.custo ?? 0)
  const data = [
    { name: "Receita PDV", value: receita },
    { name: "Custo de compra", value: custo },
    { name: "Lucro bruto", value: lucro },
  ]
  return (
    <div className="margin-hero">
      <div>
        <span>Margem bruta estimada</span>
        <strong>{percent(margem)}</strong>
        <p>Receita PDV - custo de compra = {money(lucro)}</p>
      </div>
      <ResponsiveContainer width="100%" height={220}>
        <BarChart data={data}>
          <CartesianGrid stroke={colors.grid} vertical={false} />
          <XAxis dataKey="name" tick={{ fill: colors.muted, fontSize: 12 }} />
          <YAxis tickFormatter={axisMoney} tick={{ fill: colors.muted, fontSize: 12 }} />
          <Tooltip contentStyle={tooltipStyle} formatter={(value) => money(value as number)} />
          <Bar dataKey="value" radius={[10, 10, 0, 0]}>
            <Cell fill={colors.accent} />
            <Cell fill="#60717d" />
            <Cell fill={colors.warning} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
