export function formatRelativeTime(timestamp: number | string, locale = "zh-CN"): string {
  const value = typeof timestamp === "number" ? timestamp : Date.parse(timestamp);
  const date = new Date(value < 10_000_000_000 ? value * 1000 : value);
  return new Intl.DateTimeFormat(locale, { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" }).format(date);
}
