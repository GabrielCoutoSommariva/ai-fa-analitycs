function formatBrNumber(value: number, maximumFractionDigits = 2, minimumFractionDigits = 0) {
  const fixed = value.toFixed(maximumFractionDigits)
  const trimmed = maximumFractionDigits > minimumFractionDigits ? fixed.replace(/\.?0+$/, "") : fixed
  const [integer, decimal] = trimmed.split(".")
  const grouped = integer.replace(/\B(?=(\d{3})+(?!\d))/g, ".")
  return decimal ? `${grouped},${decimal}` : grouped
}

function normalizedNumber(value: number | string | null | undefined) {
  return Number(value ?? 0)
}

export function money(value: number | string | null | undefined) {
  return `R$ ${formatBrNumber(normalizedNumber(value), 2, 2)}`
}

export function compactMoney(value: number | string | null | undefined) {
  const numeric = normalizedNumber(value)
  const abs = Math.abs(numeric)
  if (abs >= 1_000_000) return `R$ ${formatBrNumber(numeric / 1_000_000, 2)} mi`
  if (abs >= 1_000) return `R$ ${formatBrNumber(numeric / 1_000, 2)} mil`
  return money(numeric)
}

export function number(value: number | string | null | undefined, maximumFractionDigits = 2) {
  return formatBrNumber(normalizedNumber(value), maximumFractionDigits)
}

export function compactNumber(value: number | string | null | undefined, maximumFractionDigits = 1) {
  const numeric = normalizedNumber(value)
  const abs = Math.abs(numeric)
  if (abs >= 1_000_000) return `${formatBrNumber(numeric / 1_000_000, maximumFractionDigits)} mi`
  if (abs >= 1_000) return `${formatBrNumber(numeric / 1_000, maximumFractionDigits)} mil`
  return number(numeric, maximumFractionDigits)
}

export function percent(value: number | string | null | undefined) {
  return `${formatBrNumber(normalizedNumber(value) * 100, 2)}%`
}
