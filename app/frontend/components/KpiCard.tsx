import { Badge } from "./ui/badge"
import { Card } from "./ui/card"

type KpiCardProps = {
  label: string
  value: string
  baseline?: string
  baselineLabel?: string
  secondaryBaseline?: string
  secondaryBaselineLabel?: string
  note?: string
  tone?: "default" | "success" | "warning" | "danger"
}

export function KpiCard({ label, value, baseline, baselineLabel = "Rede", secondaryBaseline, secondaryBaselineLabel = "Rede", note, tone = "default" }: KpiCardProps) {
  return (
    <Card className="kpi-card">
      <div className="kpi-card__top">
        <span>{label}</span>
        {note && <Badge tone={tone}>{note}</Badge>}
      </div>
      <div className="kpi-card__value">
        <strong title={value}>{value}</strong>
        {baseline && <small title={baseline}>{baselineLabel ? `${baselineLabel}: ` : ""}{baseline}</small>}
        {secondaryBaseline && <small title={secondaryBaseline}>{secondaryBaselineLabel ? `${secondaryBaselineLabel}: ` : ""}{secondaryBaseline}</small>}
      </div>
    </Card>
  )
}
