import "./globals.css"
import { Providers } from "./providers"

export const metadata = {
  title: "Inteligência da Farmácia",
  description: "BI modular com contexto para IA"
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="pt-BR">
      <body><Providers>{children}</Providers></body>
    </html>
  )
}
