"use client"

import { Bot, MessageCircle, Send, UserRound, X } from "lucide-react"
import { type KeyboardEvent, useEffect, useRef, useState } from "react"

import { api } from "@/lib/api"
import type { AiHistoryMessage } from "@/lib/types"
import type { DateFilters } from "@/lib/types"

import { Button } from "./ui/button"

type Message = {
  role: "user" | "assistant"
  content: string
}

const INITIAL_ASSISTANT_MESSAGE = "Oi, sou o assistente BI. Pergunte sobre faturamento, lojas, ticket médio, margem ou produtos. Vou usar o período filtrado no dashboard."
const HISTORY_LIMIT = 12

const suggestions = [
  "Quanto vendi no período?",
  "Qual loja vendeu mais?",
  "Quais produtos venderam com prejuízo?",
  "Qual foi o ticket médio?"
]

function renderInline(text: string) {
  return text.split(/(\*\*.*?\*\*)/g).filter(Boolean).map((part, index) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      return <strong key={`${part}-${index}`}>{part.slice(2, -2)}</strong>
    }
    return <span key={`${part}-${index}`}>{part}</span>
  })
}

function MessageContent({ content }: { content: string }) {
  const normalized = content.replace(/\s+(?=\d+\.\s)/g, "\n")
  const lines = normalized.split("\n").map((line) => line.trim()).filter(Boolean)
  const numbered = lines.filter((line) => /^\d+\.\s/.test(line))

  if (numbered.length >= 2) {
    const intro = lines.find((line) => !/^\d+\.\s/.test(line))
    return (
      <div className="message-content">
        {intro && <p>{renderInline(intro)}</p>}
        <ol>
          {numbered.map((line) => <li key={line}>{renderInline(line.replace(/^\d+\.\s/, ""))}</li>)}
        </ol>
      </div>
    )
  }

  return <div className="message-content">{lines.map((line) => <p key={line}>{renderInline(line)}</p>)}</div>
}

function createThreadId() {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID()
  return `${Date.now()}-${Math.random().toString(36).slice(2)}`
}

function buildHistory(messages: Message[]): AiHistoryMessage[] {
  return messages
    .filter((message) => message.content.trim() && message.content !== INITIAL_ASSISTANT_MESSAGE)
    .slice(-HISTORY_LIMIT)
    .map((message) => ({ role: message.role, content: message.content }))
}

export function AiChat({ filters }: { filters: DateFilters }) {
  const [isOpen, setIsOpen] = useState(false)
  const [question, setQuestion] = useState("")
  const [messages, setMessages] = useState<Message[]>([
    { role: "assistant", content: INITIAL_ASSISTANT_MESSAGE }
  ])
  const [isLoading, setIsLoading] = useState(false)
  const threadIdRef = useRef(createThreadId())
  const messagesStateRef = useRef<Message[]>(messages)
  const messagesRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    messagesStateRef.current = messages
  }, [messages])

  useEffect(() => {
    messagesRef.current?.scrollTo({ top: messagesRef.current.scrollHeight, behavior: "smooth" })
  }, [messages, isOpen])

  function appendMessage(message: Message) {
    setMessages((current) => {
      const next = [...current, message]
      messagesStateRef.current = next
      return next
    })
  }

  async function submit(value = question) {
    if (isLoading) return
    const clean = value.trim()
    if (!clean) return
    const history = buildHistory(messagesStateRef.current)
    setQuestion("")
    resetTextarea()
    setIsLoading(true)
    appendMessage({ role: "user", content: clean })
    try {
      const route = await api.ask(clean, filters, history, threadIdRef.current)
      const content = route.answer ?? (route.status === "answered" ? "Pergunta respondida." : route.message ?? "Não consegui responder.")
      appendMessage({ role: "assistant", content })
    } catch (error) {
      appendMessage({ role: "assistant", content: error instanceof Error ? error.message : "Erro ao analisar pergunta." })
    } finally {
      setIsLoading(false)
    }
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault()
      submit()
    }
  }

  function resizeTextarea(element: HTMLTextAreaElement) {
    element.style.height = "52px"
    const height = Math.min(element.scrollHeight, 132)
    element.style.height = `${height}px`
    element.style.overflowY = element.scrollHeight > 132 ? "auto" : "hidden"
  }

  function resetTextarea() {
    if (!textareaRef.current) return
    textareaRef.current.style.height = "52px"
    textareaRef.current.style.overflowY = "hidden"
  }

  if (!isOpen) {
    return (
      <button className="floating-chat-button" onClick={() => setIsOpen(true)} aria-label="Abrir chat de IA">
        <MessageCircle size={22} />
        <span>IA</span>
      </button>
    )
  }

  return (
    <section className="chat-panel" aria-label="Chat BI com IA">
      <div className="chat-panel__header">
        <div>
          <h2>Chat farmácia</h2>
        </div>
        <div className="chat-panel__actions">
          <button className="chat-close" onClick={() => setIsOpen(false)} aria-label="Fechar chat"><X size={18} /></button>
        </div>
      </div>

      <div className="suggestions">
        {suggestions.map((item) => <button key={item} disabled={isLoading} onClick={() => submit(item)}>{item}</button>)}
      </div>

      <div className="messages" ref={messagesRef}>
        {messages.map((message, index) => (
          <div className={`message message--${message.role}`} key={`${message.role}-${index}`}>
            <div className="avatar">{message.role === "assistant" ? <Bot size={16} /> : <UserRound size={16} />}</div>
            <div className="bubble">
              <MessageContent content={message.content} />
            </div>
          </div>
        ))}
        {isLoading && (
          <div className="message message--assistant">
            <div className="avatar"><Bot size={16} /></div>
            <div className="bubble bubble--typing" aria-label="Chat farmácia digitando">
              <span></span>
              <span></span>
              <span></span>
            </div>
          </div>
        )}
      </div>

      <div className="chat-input">
        <textarea
          ref={textareaRef}
          value={question}
          onChange={(event) => {
            setQuestion(event.target.value)
            resizeTextarea(event.target)
          }}
          onKeyDown={handleKeyDown}
          placeholder="Digite sua pergunta..."
        />
        <Button onClick={() => submit()} disabled={isLoading}><Send size={16} /> {isLoading ? "Analisando" : "Enviar"}</Button>
      </div>
    </section>
  )
}
