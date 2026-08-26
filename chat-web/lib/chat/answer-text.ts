import type { ChatBlockDTO } from "@/types/chat";
import { blockAssociatedValue } from "@/lib/chat/block-normalizer";

/** 复制/朗读允许进入的正文种类（与回合正文归类一致）。 */
const ANSWER_TEXT_KINDS: ReadonlySet<string> = new Set(["text", "html", "translatedText"]);

function asString(value: unknown): string {
  return typeof value === "string" ? value : "";
}

/** 从 associate value 提取可见文案，兼容 string 与对象形态（html/translatedText）。 */
function textOf(block: ChatBlockDTO): string {
  const value = blockAssociatedValue(block);
  if (typeof value === "string") return value;
  if (!value || typeof value !== "object") return "";
  const record = value as Record<string, unknown>;
  return asString(record.text) || asString(record.content) || asString(record.target) || asString(record.translated) || asString(record.html);
}

/**
 * 能力五：从回合 Block 中提取“最终可见正文”。仅取 timeline 的 content 类块，
 * 排除工具参数、结构化结果卡、Trace、tool/toolPresentation 子块与隐藏 thinking 内容。
 */
export function extractAnswerText(blocks: ChatBlockDTO[]): string {
  return blocks
    .filter((block) => block.node_role === "timeline" && ANSWER_TEXT_KINDS.has(block.kind))
    .map((block) => textOf(block).trim())
    .filter(Boolean)
    .join("\n\n");
}