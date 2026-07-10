"use client"

import { AlertCircle, Bug, CheckCircle2, ImagePlus, Send, X } from "lucide-react"
import { type FormEvent, useState } from "react"

import { api } from "@/lib/api"
import type { DateFilters, SessionUser } from "@/lib/types"

import { Button } from "./ui/button"


type ProblemReportButtonProps = {
  filters: DateFilters
  user?: SessionUser | null
}


const initialForm = {
  title: "",
  category: "problema",
  severity: "media",
  contactEmail: "",
  description: ""
}

const maxImageBytes = 1.5 * 1024 * 1024

type Attachment = {
  name: string
  type: string
  content: string
}


export function ProblemReportButton({ filters, user }: ProblemReportButtonProps) {
  const [isOpen, setIsOpen] = useState(false)
  const [form, setForm] = useState(initialForm)
  const [isSending, setIsSending] = useState(false)
  const [status, setStatus] = useState<{ type: "success" | "error"; message: string } | null>(null)
  const [attachment, setAttachment] = useState<Attachment | null>(null)
  const [fileInputKey, setFileInputKey] = useState(0)

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (isSending) return

    setStatus(null)
    setIsSending(true)
    try {
      const response = await api.reportProblem({
        title: form.title.trim(),
        description: form.description.trim(),
        category: form.category,
        severity: form.severity,
        contact_email: form.contactEmail.trim() || user?.email || null,
        page_url: typeof window === "undefined" ? null : window.location.href,
        filters: {
          data_inicio: filters.dataInicio,
          data_fim: filters.dataFim,
          cnpj: filters.cnpj
        },
        attachment_name: attachment?.name ?? null,
        attachment_type: attachment?.type ?? null,
        attachment_content: attachment?.content ?? null
      })
      setStatus({ type: "success", message: response.message })
      setForm({ ...initialForm, contactEmail: user?.email ?? "" })
      setAttachment(null)
      setFileInputKey((current) => current + 1)
    } catch (error) {
      setStatus({ type: "error", message: error instanceof Error ? error.message : "Nao foi possivel enviar o reporte." })
    } finally {
      setIsSending(false)
    }
  }

  function openForm() {
    setStatus(null)
    setForm((current) => ({ ...current, contactEmail: current.contactEmail || user?.email || "" }))
    setIsOpen(true)
  }

  function handleImageChange(file: File | undefined) {
    setStatus(null)
    if (!file) {
      setAttachment(null)
      return
    }
    if (!file.type.startsWith("image/")) {
      setStatus({ type: "error", message: "Anexe apenas imagens." })
      setAttachment(null)
      setFileInputKey((current) => current + 1)
      return
    }
    if (file.size > maxImageBytes) {
      setStatus({ type: "error", message: "A imagem deve ter no máximo 1,5 MB." })
      setAttachment(null)
      setFileInputKey((current) => current + 1)
      return
    }

    const reader = new FileReader()
    reader.onload = () => {
      if (typeof reader.result !== "string") return
      setAttachment({ name: file.name, type: file.type, content: reader.result })
    }
    reader.onerror = () => setStatus({ type: "error", message: "Não foi possível ler a imagem." })
    reader.readAsDataURL(file)
  }

  if (!isOpen) {
    return (
      <button className="floating-report-button" onClick={openForm} aria-label="Reportar problema">
        <Bug size={19} />
        <span>Reportar problema</span>
      </button>
    )
  }

  return (
    <section className="report-panel" aria-label="Reportar problema">
      <div className="report-panel__header">
        <div>
          <h2>Reportar problema</h2>
          <p>Envie erro, dúvida de dado ou problema de acesso para o suporte.</p>
        </div>
        <button className="chat-close" onClick={() => setIsOpen(false)} aria-label="Fechar reporte"><X size={18} /></button>
      </div>

      <form className="report-form" onSubmit={submit}>
        <label>
          Título
          <input
            value={form.title}
            minLength={4}
            maxLength={140}
            required
            onChange={(event) => setForm({ ...form, title: event.target.value })}
            placeholder="Ex.: gráfico de lojas não carregou"
          />
        </label>

        <div className="report-form__grid">
          <label>
            Categoria
            <select value={form.category} onChange={(event) => setForm({ ...form, category: event.target.value })}>
              <option value="problema">Problema</option>
              <option value="dados">Divergência de dados</option>
              <option value="acesso">Acesso</option>
              <option value="sugestao">Sugestão</option>
            </select>
          </label>
          <label>
            Prioridade
            <select value={form.severity} onChange={(event) => setForm({ ...form, severity: event.target.value })}>
              <option value="baixa">Baixa</option>
              <option value="media">Média</option>
              <option value="alta">Alta</option>
              <option value="critica">Crítica</option>
            </select>
          </label>
        </div>

        <label>
          Email para retorno
          <input
            type="email"
            value={form.contactEmail}
            maxLength={180}
            onChange={(event) => setForm({ ...form, contactEmail: event.target.value })}
            placeholder="seu@email.com"
          />
        </label>

        <label>
          Descrição
          <textarea
            value={form.description}
            minLength={12}
            maxLength={4000}
            required
            onChange={(event) => setForm({ ...form, description: event.target.value })}
            placeholder="Descreva o que aconteceu, o que esperava ver e se é possível reproduzir."
          />
        </label>

        <label>
          Imagem opcional
          <input
            key={fileInputKey}
            type="file"
            accept="image/png,image/jpeg,image/webp"
            onChange={(event) => handleImageChange(event.target.files?.[0])}
          />
        </label>

        {attachment && (
          <div className="report-attachment">
            <ImagePlus size={16} />
            <span>{attachment.name}</span>
            <button type="button" onClick={() => { setAttachment(null); setFileInputKey((current) => current + 1) }}>Remover</button>
          </div>
        )}

        <div className="report-context">
          Filtro enviado: {filters.dataInicio || "sem início"} até {filters.dataFim || "sem fim"}{filters.cnpj ? `, CNPJ ${filters.cnpj}` : ""}.
        </div>

        {status && (
          <div className={`report-status report-status--${status.type}`}>
            {status.type === "success" ? <CheckCircle2 size={16} /> : <AlertCircle size={16} />}
            {status.message}
          </div>
        )}

        <Button type="submit" disabled={isSending}>
          <Send size={16} /> {isSending ? "Enviando" : "Enviar reporte"}
        </Button>
      </form>
    </section>
  )
}
