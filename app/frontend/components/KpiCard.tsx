import { Badge } from "./ui/badge"
import { Card } from "./ui/card"

type KpiCardProps = {
  label: string
  value: string
  note?: string
  tone?: "default" | "success" | "warning" | "danger"
}

export function KpiCard({ label, value, note, tone = "default" }: KpiCardProps) {
  return (
    <Card className="kpi-card">
      <div className="kpi-card__top">
        <span>{label}</span>
        {note && <Badge tone={tone}>{note}</Badge>}
      </div>
      <strong title={value}>{value}</strong>
    </Card>
  )
}
