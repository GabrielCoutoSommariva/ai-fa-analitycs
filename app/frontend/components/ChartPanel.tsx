import type { ReactNode } from "react"

import { Badge } from "./ui/badge"

type ChartPanelProps = {
  title: string
  subtitle?: string
  badge?: string
  isLoading?: boolean
  children: ReactNode
}

export function ChartPanel({ title, subtitle, badge, isLoading = false, children }: ChartPanelProps) {
  return (
    <section className="chart-panel">
      <div className="chart-panel__header">
        <div>
          <h2>{title}</h2>
          {subtitle && <p>{subtitle}</p>}
        </div>
        {badge && <Badge tone="warning">{badge}</Badge>}
      </div>
      <div className="chart-panel__body">
        {isLoading ? <div className="chart-loading"><i></i> Carregando dados...</div> : children}
      </div>
    </section>
  )
}
