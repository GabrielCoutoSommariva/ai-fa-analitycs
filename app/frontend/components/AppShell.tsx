import { BarChart3, Building2, DollarSign, PackageSearch, ShoppingCart } from "lucide-react"

export type DashboardSection = "overview" | "sales" | "stores" | "products" | "margin"

const nav: Array<{ id: DashboardSection; label: string; icon: typeof BarChart3 }> = [
  { id: "overview", label: "Visão geral", icon: BarChart3 },
  { id: "sales", label: "Vendas", icon: ShoppingCart },
  { id: "stores", label: "Lojas", icon: Building2 },
  { id: "products", label: "Produtos", icon: PackageSearch },
  { id: "margin", label: "Margem", icon: DollarSign }
]

type AppShellProps = {
  activeSection: DashboardSection
  onSectionChange: (section: DashboardSection) => void
  children: React.ReactNode
}

export function AppShell({ activeSection, onSectionChange, children }: AppShellProps) {
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <img src="/assets/logo-colored.webp" alt="Inteligência da Farmácia" />
        </div>
        <nav>
          {nav.map((item) => {
            const Icon = item.icon
            return <button className={activeSection === item.id ? "active" : ""} key={item.id} onClick={() => onSectionChange(item.id)}><Icon size={18} /> {item.label}</button>
          })}
        </nav>
      </aside>
      <div className="workspace">{children}</div>
    </div>
  )
}
