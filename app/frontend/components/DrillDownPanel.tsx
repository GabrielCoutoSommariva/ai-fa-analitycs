"use client"

import { ChevronDown } from "lucide-react"
import type { ReactNode } from "react"

import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "./ui/collapsible"

type DrillDownPanelProps = {
  title: string
  subtitle?: string
  children: ReactNode
}

export function DrillDownPanel({ title, subtitle, children }: DrillDownPanelProps) {
  return (
    <Collapsible className="drill-panel">
      <CollapsibleTrigger className="drill-trigger">
        <div>
          <strong>{title}</strong>
          {subtitle && <span>{subtitle}</span>}
        </div>
        <ChevronDown size={18} />
      </CollapsibleTrigger>
      <CollapsibleContent className="drill-content">
        {children}
      </CollapsibleContent>
    </Collapsible>
  )
}
