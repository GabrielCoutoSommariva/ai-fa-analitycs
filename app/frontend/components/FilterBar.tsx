"use client"

import { useQuery } from "@tanstack/react-query"
import { useEffect, useState } from "react"

import { api } from "@/lib/api"
import type { DateFilters } from "@/lib/types"

import { Button } from "./ui/button"

type FilterBarProps = {
  filters: DateFilters
  setFilters: (filters: DateFilters) => void
  onRefresh: () => void
  isLoading?: boolean
}

export function FilterBar({ filters, setFilters, onRefresh, isLoading }: FilterBarProps) {
  const [isMounted, setIsMounted] = useState(false)
  const cnpjs = useQuery({ queryKey: ["lojasCnpj"], queryFn: api.lojasCnpj })
  const salesPeriod = useQuery({ queryKey: ["salesPeriod"], queryFn: api.salesPeriod })
  const selectedDigits = filters.cnpj.replace(/\D/g, "")
  const selectedCnpj = cnpjs.data?.find((item) => item.cnpj_digits === selectedDigits || item.cnpj === filters.cnpj)
  const fullStart = salesPeriod.data?.data_inicio ?? ""
  const fullEnd = salesPeriod.data?.data_fim ?? ""
  const isFullPeriod = Boolean(fullStart && fullEnd && filters.dataInicio === fullStart && filters.dataFim === fullEnd)

  useEffect(() => {
    setIsMounted(true)
  }, [])

  return (
    <section className="filter-bar">
      <label>
        Data inicio
        <input type="date" value={filters.dataInicio} onChange={(event) => setFilters({ ...filters, dataInicio: event.target.value })} />
      </label>
      <label>
        Data fim
        <input type="date" value={filters.dataFim} onChange={(event) => setFilters({ ...filters, dataFim: event.target.value })} />
      </label>
      <label>
        CNPJ da loja
        <input list="lojas-cnpj" placeholder="Todos" value={filters.cnpj} onChange={(event) => setFilters({ ...filters, cnpj: event.target.value })} />
        <datalist id="lojas-cnpj">
          {(cnpjs.data ?? []).map((item) => <option key={item.cnpj_digits} value={item.cnpj}>{item.lojas} loja(s)</option>)}
        </datalist>
        {selectedCnpj && <span className="filter-hint">{selectedCnpj.lojas} loja(s) vinculada(s)</span>}
      </label>
      <Button className="filter-clear" variant="ghost" onClick={() => setFilters({ ...filters, dataInicio: fullStart, dataFim: fullEnd })} disabled={!isMounted || !fullStart || !fullEnd || isFullPeriod}>
        Período completo
      </Button>
      <Button onClick={onRefresh}>{isLoading ? "Atualizando..." : "Atualizar"}</Button>
    </section>
  )
}
