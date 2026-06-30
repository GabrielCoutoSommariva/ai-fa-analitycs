"use client"

import {
  ColumnDef,
  ColumnFiltersState,
  SortingState,
  VisibilityState,
  flexRender,
  getCoreRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  useReactTable
} from "@tanstack/react-table"
import { ChevronLeft, ChevronRight, ChevronsUpDown, SlidersHorizontal } from "lucide-react"
import { useState } from "react"

import { Button } from "./ui/button"
import { DropdownMenu, DropdownMenuCheckboxItem, DropdownMenuContent, DropdownMenuTrigger } from "./ui/dropdown-menu"

type DataTableProps<TData> = {
  columns: ColumnDef<TData>[]
  data: TData[]
  isLoading?: boolean
  searchPlaceholder?: string
  title: string
  source?: string
}

function columnLabel<TData>(column: ReturnType<ReturnType<typeof useReactTable<TData>>["getAllColumns"]>[number]) {
  const header = column.columnDef.header
  return typeof header === "string" ? header : column.id
}

export function DataTable<TData>({ columns, data, isLoading = false, searchPlaceholder = "Buscar...", title, source }: DataTableProps<TData>) {
  const [sorting, setSorting] = useState<SortingState>([])
  const [columnFilters, setColumnFilters] = useState<ColumnFiltersState>([])
  const [columnVisibility, setColumnVisibility] = useState<VisibilityState>({})
  const [globalFilter, setGlobalFilter] = useState("")

  const table = useReactTable({
    data,
    columns,
    state: { sorting, columnFilters, columnVisibility, globalFilter },
    onSortingChange: setSorting,
    onColumnFiltersChange: setColumnFilters,
    onColumnVisibilityChange: setColumnVisibility,
    onGlobalFilterChange: setGlobalFilter,
    getCoreRowModel: getCoreRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getPaginationRowModel: getPaginationRowModel()
  })

  return (
    <section className="table-panel">
      <div className="table-panel__header">
        <div>
          <h2>{title}</h2>
          {source && <p>Fonte: {source}</p>}
        </div>
        <div className="table-actions">
          <input value={globalFilter} onChange={(event) => setGlobalFilter(event.target.value)} placeholder={searchPlaceholder} />
          <DropdownMenu>
            <DropdownMenuTrigger asChild><Button variant="secondary"><SlidersHorizontal size={16} /> Colunas</Button></DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              {table.getAllColumns().filter((column) => column.getCanHide()).map((column) => (
                <DropdownMenuCheckboxItem key={column.id} checked={column.getIsVisible()} onCheckedChange={(value) => column.toggleVisibility(!!value)}>
                  {columnLabel(column)}
                </DropdownMenuCheckboxItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>

      <div className="table-wrap">
        <table>
          <thead>
            {table.getHeaderGroups().map((headerGroup) => (
              <tr key={headerGroup.id}>
                {headerGroup.headers.map((header) => (
                  <th key={header.id}>
                    {header.isPlaceholder ? null : (
                      <button className="th-button" onClick={header.column.getToggleSortingHandler()}>
                        {flexRender(header.column.columnDef.header, header.getContext())}
                        <ChevronsUpDown size={14} />
                      </button>
                    )}
                  </th>
                ))}
              </tr>
            ))}
          </thead>
          <tbody>
            {isLoading ? (
              <tr>
                <td colSpan={columns.length} className="loading-cell">
                  <span className="table-loading"><i></i> Carregando dados...</span>
                </td>
              </tr>
            ) : table.getRowModel().rows.length ? table.getRowModel().rows.map((row) => (
              <tr key={row.id}>
                {row.getVisibleCells().map((cell) => <td key={cell.id}>{flexRender(cell.column.columnDef.cell, cell.getContext())}</td>)}
              </tr>
            )) : (
              <tr><td colSpan={columns.length} className="empty-cell">Sem dados para o filtro atual.</td></tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="table-footer">
        <span>{table.getFilteredRowModel().rows.length} registros</span>
        <div>
          <Button variant="ghost" onClick={() => table.previousPage()} disabled={!table.getCanPreviousPage()}><ChevronLeft size={16} /></Button>
          <span>Página {table.getState().pagination.pageIndex + 1} de {table.getPageCount() || 1}</span>
          <Button variant="ghost" onClick={() => table.nextPage()} disabled={!table.getCanNextPage()}><ChevronRight size={16} /></Button>
        </div>
      </div>
    </section>
  )
}
