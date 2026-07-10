"use client"

import { useQuery } from "@tanstack/react-query"
import { ChevronDown } from "lucide-react"
import { useEffect, useMemo, useRef, useState } from "react"

import { api } from "@/lib/api"
import type { DateFilters, SessionStore } from "@/lib/types"

import { Button } from "./ui/button"

function formatCnpj(value: string) {
  const digits = value.replace(/\D/g, "")
  if (digits.length !== 14) return value
  return digits.replace(/(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})/, "$1.$2.$3/$4-$5")
}

function previousMonthStartFromDate(value: string | null | undefined) {
  if (!value || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return ""
  const year = Number(value.slice(0, 4))
  const month = Number(value.slice(5, 7))
  const previousYear = month === 1 ? year - 1 : year
  const previousMonth = month === 1 ? 12 : month - 1
  return `${previousYear}-${String(previousMonth).padStart(2, "0")}-01`
}

type FilterBarProps = {
  filters: DateFilters
  setFilters: (filters: DateFilters) => void
  onRefresh: () => void
  isLoading?: boolean
  authorizedStores?: SessionStore[]
}

export function FilterBar({ filters, setFilters, onRefresh, isLoading, authorizedStores }: FilterBarProps) {
  const [isMounted, setIsMounted] = useState(false)
  const [isCnpjOpen, setIsCnpjOpen] = useState(false)
  const [selectedOptionKey, setSelectedOptionKey] = useState<string | null>(null)
  const cnpjPickerRef = useRef<HTMLDivElement>(null)
  const cnpjs = useQuery({ queryKey: ["lojasCnpj"], queryFn: api.lojasCnpj })
  const allowedCnpjs = new Set(authorizedStores?.map((store) => store.cnpj.replace(/\D/g, "")) ?? [])
  const cnpjOptions = (cnpjs.data ?? []).filter((item) => !authorizedStores?.length || allowedCnpjs.has(item.cnpj_digits))
  const storeOptions = useMemo(() => cnpjOptions.flatMap((item) => {
    if (authorizedStores?.length) return []
    const stores = item.lojas_vinculadas.length ? item.lojas_vinculadas : [{ loja_id: 0, loja: `${item.lojas} loja(s)` }]
    return stores.map((store) => ({
      key: `${item.cnpj_digits}-${store.loja_id}-${store.loja}`,
      cnpj: item.cnpj,
      cnpjDigits: item.cnpj_digits,
      linkedStores: Number(item.lojas) || stores.length,
      loja: store.loja
    }))
  }).concat((authorizedStores ?? []).flatMap((store, index) => {
    const digits = store.cnpj.replace(/\D/g, "")
    if (!digits) return []
    const dataOption = cnpjOptions.find((item) => item.cnpj_digits === digits)
    const loja = store.nomeFantasia?.trim() || dataOption?.lojas_vinculadas[0]?.loja || `Loja ${formatCnpj(digits)}`
    return [{
      key: `${digits}-${index}-${loja}`,
      cnpj: store.cnpj,
      cnpjDigits: digits,
      linkedStores: Number(dataOption?.lojas) || 1,
      loja
    }]
  })), [authorizedStores, cnpjOptions])
  const salesPeriod = useQuery({ queryKey: ["salesPeriod"], queryFn: api.salesPeriod })
  const selectedDigits = filters.cnpj.replace(/\D/g, "")
  const selectedCnpj = cnpjOptions.find((item) => item.cnpj_digits === selectedDigits || item.cnpj === filters.cnpj)
  const selectedOption = storeOptions.find((item) => item.key === selectedOptionKey && item.cnpjDigits === selectedDigits) ?? storeOptions.find((item) => item.cnpjDigits === selectedDigits)
  const totalStores = storeOptions.length || cnpjOptions.reduce((total, item) => total + Number(item.lojas || 0), 0)
  const selectedStoreCount = selectedOption?.linkedStores ?? Number(selectedCnpj?.lojas || 0)
  const storeCountLabel = selectedDigits && selectedStoreCount ? `${selectedStoreCount} loja(s) vinculada(s)` : `${totalStores} loja(s) disponível(is)`
  const loadedEnd = salesPeriod.data?.data_fim ?? ""
  const loadedRangeStart = previousMonthStartFromDate(loadedEnd)
  const isLoadedRange = Boolean(loadedRangeStart && loadedEnd && filters.dataInicio === loadedRangeStart && filters.dataFim === loadedEnd)

  useEffect(() => {
    setIsMounted(true)
  }, [])

  useEffect(() => {
    function closeOnOutsideClick(event: MouseEvent) {
      if (!cnpjPickerRef.current?.contains(event.target as Node)) {
        setIsCnpjOpen(false)
      }
    }

    document.addEventListener("mousedown", closeOnOutsideClick)
    return () => document.removeEventListener("mousedown", closeOnOutsideClick)
  }, [])

  useEffect(() => {
    if (!selectedDigits) setSelectedOptionKey(null)
  }, [selectedDigits])

  return (
    <section className="filter-bar">
      <label>
        Data início
        <input type="date" value={filters.dataInicio} onChange={(event) => setFilters({ ...filters, dataInicio: event.target.value })} />
      </label>
      <label>
        Data fim
        <input type="date" value={filters.dataFim} onChange={(event) => setFilters({ ...filters, dataFim: event.target.value })} />
      </label>
      <div className="filter-field cnpj-picker-field" ref={cnpjPickerRef}>
        <span className="filter-label">CNPJ da loja</span>
        <span className="filter-hint cnpj-count">{storeCountLabel}</span>
        <button
          className={`cnpj-trigger ${isCnpjOpen ? "is-open" : ""}`}
          type="button"
          onClick={() => setIsCnpjOpen((current) => !current)}
          aria-expanded={isCnpjOpen}
          aria-haspopup="listbox"
        >
          <span>{selectedOption ? `${selectedOption.loja} (${formatCnpj(selectedOption.cnpj)})` : "Todos"}</span>
          <ChevronDown size={16} />
        </button>
        {isCnpjOpen && (
          <div className="cnpj-options" role="listbox">
            <button
              className={!selectedDigits ? "active" : ""}
              type="button"
              role="option"
              aria-selected={!selectedDigits}
              onClick={() => {
                setFilters({ ...filters, cnpj: "" })
                setSelectedOptionKey(null)
                setIsCnpjOpen(false)
              }}
            >
              <strong>Todos</strong>
              <span>Consolidar lojas autorizadas.</span>
            </button>
            {storeOptions.map((item) => (
              <button
                className={selectedOption?.key === item.key ? "active" : ""}
                key={item.key}
                type="button"
                role="option"
                aria-selected={selectedOption?.key === item.key}
                onClick={() => {
                  setFilters({ ...filters, cnpj: item.cnpj })
                  setSelectedOptionKey(item.key)
                  setIsCnpjOpen(false)
                }}
              >
                <strong>{item.loja} ({formatCnpj(item.cnpj)})</strong>
                {item.linkedStores > 1 && <span>{item.linkedStores} lojas vinculadas a este CNPJ.</span>}
              </button>
            ))}
          </div>
        )}
      </div>
      <Button className="filter-clear" variant="ghost" onClick={() => setFilters({ ...filters, dataInicio: loadedRangeStart, dataFim: loadedEnd })} disabled={!isMounted || !loadedRangeStart || !loadedEnd || isLoadedRange}>
        Mês anterior até hoje
      </Button>
      <Button onClick={onRefresh}>{isLoading ? "Atualizando..." : "Atualizar"}</Button>
    </section>
  )
}
