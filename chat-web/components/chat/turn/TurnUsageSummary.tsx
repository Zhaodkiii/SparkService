import type { TurnUsageSummary as TurnUsage } from "@/types/chat";

function currencySymbol(currency: string): string {
  const code = currency.trim().toUpperCase();
  if (code === "CNY") return "¥";
  if (code === "USD") return "$";
  if (code === "EUR") return "€";
  return code;
}

/**
 * 回合用量摘要（能力五）：Token / 模型调用 / 工具次数 / 费用。
 * 费用仅在 `amount`、`currency`、`price_version` 同时存在时展示，避免显示伪 0。
 */
export function TurnUsageSummary({ usage }: { usage: TurnUsage | null }) {
  if (!usage) return null;
  const hasTokens = usage.prompt_tokens != null || usage.completion_tokens != null || usage.reasoning_tokens != null;
  const hasCost = Boolean(usage.amount && usage.currency && usage.price_version);
  const hasCalls = usage.model_calls != null || usage.tool_calls != null;
  if (!hasTokens && !hasCost && !hasCalls) return null;

  return <div className="turn-usage">
    {hasTokens && <span className="turn-usage__tokens">{(usage.prompt_tokens ?? 0).toLocaleString()} / {(usage.completion_tokens ?? 0).toLocaleString()} tokens</span>}
    {usage.model_calls != null && <span className="turn-usage__item">模型调用 {usage.model_calls}</span>}
    {usage.tool_calls != null && <span className="turn-usage__item">工具 {usage.tool_calls}</span>}
    {hasCost && <span className="turn-usage__cost">{currencySymbol(usage.currency!)} {usage.amount}</span>}
  </div>;
}