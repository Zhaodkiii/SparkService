import type { ToolActivityDTO, ToolErrorDTO } from "@/types/tool";

/**
 * P4 activity projection: the single source of user-facing tool copy.
 *
 * The wire data is already desensitized server-side; this layer adds the
 * presentation contract — status labels, argument summary lines, error copy
 * keyed by message_key, and graceful degradation for unknown values. It never
 * concatenates raw wire fields into copy: unknown names/codes always map to
 * generic fallbacks so a newer server cannot leak anything by omission here.
 */

export type ToolActivityTone = "neutral" | "active" | "success" | "error" | "muted";

export interface ToolActivityViewModel {
  toolCallId: string;
  displayName: string;
  statusLabel: string;
  tone: ToolActivityTone;
  argSummary: string | null;
  resultLine: string | null;
  errorLine: string | null;
  retryable: boolean;
  duplicate: boolean;
  isTerminal: boolean;
  sourceCount: number;
  startedAt: string | null;
  finishedAt: string | null;
}

/** Known tool names (P4 catalog). Unknown names degrade to generic copy. */
const KNOWN_TOOL_NAMES: ReadonlySet<string> = new Set([
  "get_current_member",
  "query_member_profile",
  "list_member_health_sources",
  "get_health_resource_context",
  "read_source",
  "search_knowledge_bag",
]);

const STATUS_LABELS: Record<ToolActivityDTO["status"], string> = {
  requested: "准备调用",
  running: "执行中",
  completed: "已完成",
  failed: "执行失败",
  cancelled: "已取消",
};

const STATUS_TONES: Record<ToolActivityDTO["status"], ToolActivityTone> = {
  requested: "neutral",
  running: "active",
  completed: "success",
  failed: "error",
  cancelled: "muted",
};

/** Web-side mirror of the server message_key table for degraded offline copy. */
const ERROR_COPY: Record<string, { text: string; retryable: boolean }> = {
  tool_invalid_arguments: { text: "工具参数不符合要求", retryable: false },
  tool_schema_validation_failed: { text: "工具调用未通过校验", retryable: false },
  tool_not_available: { text: "该工具当前不可用", retryable: false },
  tool_duplicate_call: { text: "重复的工具调用已合并", retryable: false },
  tool_call_limit: { text: "已达到本轮工具调用上限", retryable: false },
  tool_timeout: { text: "工具执行超时", retryable: true },
  tool_execution_failed: { text: "工具暂时不可用", retryable: true },
  tool_unavailable: { text: "该工具当前不可用", retryable: false },
  chat_attachment_content_unavailable: { text: "附件内容暂时无法读取", retryable: false },
};

const GENERIC_ERROR: { text: string; retryable: boolean } = { text: "工具执行出现问题", retryable: true };

export function toolErrorCopy(error: ToolErrorDTO | null): { text: string; retryable: boolean } {
  if (!error) return GENERIC_ERROR;
  return ERROR_COPY[error.message_key] ?? GENERIC_ERROR;
}

function joinList(values: string[]): string {
  return values.filter(Boolean).slice(0, 4).join("、");
}

/**
 * Human summary of the allow-listed display_args. These are already translated
 * labels from the server; we only join them, never interpret unknown shapes.
 */
function argSummary(activity: ToolActivityDTO): string | null {
  const args = activity.display_args ?? {};
  const sections = Array.isArray(args.sections) ? args.sections.map((item) => String(item)) : [];
  if (sections.length) return `读取：${joinList(sections)}`;
  const types = Array.isArray(args.resource_types) ? args.resource_types.map((item) => String(item)) : [];
  if (types.length) return `资料类型：${joinList(types)}`;
  if (typeof args.resource_type === "string" && args.resource_type) return `资料类型：${args.resource_type}`;
  if (typeof args.source_id === "string" && args.source_id) return `资料：${args.source_id}`;
  if (typeof args.query === "string" && args.query) return `检索：${args.query}`;
  if (typeof args.limit === "number") return `最多返回 ${args.limit} 项`;
  return null;
}

export function projectToolActivity(activity: ToolActivityDTO): ToolActivityViewModel {
  const known = KNOWN_TOOL_NAMES.has(activity.name);
  const displayName = known ? activity.display_name : "服务工具";
  const error = activity.error ? toolErrorCopy(activity.error) : null;
  return {
    toolCallId: activity.tool_call_id,
    displayName,
    statusLabel: STATUS_LABELS[activity.status] ?? "工具调用",
    tone: STATUS_TONES[activity.status] ?? "neutral",
    argSummary: argSummary(activity),
    resultLine: activity.result_preview,
    errorLine: error?.text ?? null,
    retryable: activity.error?.retryable ?? false,
    duplicate: Boolean(activity.duplicate_of),
    isTerminal: ["completed", "failed", "cancelled"].includes(activity.status),
    sourceCount: activity.source_refs?.length ?? 0,
    startedAt: activity.started_at,
    finishedAt: activity.finished_at,
  };
}

/** Compact single line for the activity panel timeline. */
export function toolActivityLine(view: ToolActivityViewModel): string {
  if (view.errorLine) return `${view.displayName} · ${view.errorLine}`;
  if (view.resultLine) return `${view.displayName} · ${view.resultLine}`;
  return `${view.displayName} · ${view.statusLabel}`;
}

/**
 * CHAT-WEB-027 W3: DeepTutor-aligned tool trace row model (verb/chip/detail
 * separated, mirroring DeepTutor's `describeToolCall` action-verb + artifact
 * chip pattern) rather than one pre-joined summary string. Built on top of
 * {@link projectToolActivity} — same desensitized `display_args`/`error`
 * inputs, no new raw data exposed.
 */
export interface ToolTraceViewModel extends ToolActivityViewModel {
  /** Human action verb, e.g. "读取健康资料". Falls back to displayName for
   * tools without a specific verb mapping (keeps unknown tools legible). */
  verb: string;
  /** Compact artifact chip naming what the call acted on, or null. */
  chip: string | null;
  /** Extra detail only surfaced once the row is expanded in a terminal
   * state (full result/error text + source count), never shown while the
   * call is still in flight. */
  detail: string | null;
}

/** Known-tool action verbs (P4 catalog). Unknown tools fall back to displayName. */
const TOOL_VERBS: Record<string, string> = {
  get_current_member: "确认当前用户",
  query_member_profile: "查询会员档案",
  list_member_health_sources: "列出健康资料",
  get_health_resource_context: "读取健康资料",
  read_source: "读取资料来源",
  search_knowledge_bag: "检索知识库",
};

/** Artifact chip: the same allow-listed `display_args` as {@link argSummary},
 * without its human-readable prefix ("读取："/"资料类型：" &c.) so it can sit
 * in a compact chip next to the verb instead of repeating it in prose. */
function toolChip(activity: ToolActivityDTO): string | null {
  const args = activity.display_args ?? {};
  const sections = Array.isArray(args.sections) ? args.sections.map((item) => String(item)) : [];
  if (sections.length) return joinList(sections);
  const types = Array.isArray(args.resource_types) ? args.resource_types.map((item) => String(item)) : [];
  if (types.length) return joinList(types);
  if (typeof args.resource_type === "string" && args.resource_type) return args.resource_type;
  if (typeof args.source_id === "string" && args.source_id) return args.source_id;
  if (typeof args.limit === "number") return `最多 ${args.limit} 项`;
  return null;
}

function toolTraceDetail(base: ToolActivityViewModel): string | null {
  if (!base.isTerminal) return null;
  const summary = base.errorLine ?? base.resultLine;
  if (!summary) return null;
  const parts = [summary];
  if (base.sourceCount > 0) parts.push(`引用 ${base.sourceCount} 条资料`);
  return parts.join(" · ");
}

export function projectToolTrace(activity: ToolActivityDTO): ToolTraceViewModel {
  const base = projectToolActivity(activity);
  const known = KNOWN_TOOL_NAMES.has(activity.name);
  const verb = known ? TOOL_VERBS[activity.name] ?? base.displayName : base.displayName;
  return { ...base, verb, chip: toolChip(activity), detail: toolTraceDetail(base) };
}
