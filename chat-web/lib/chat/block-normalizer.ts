import type { ChatBlockAnchor, ChatBlockDTO } from "@/types/chat";
import { CHAT_BLOCK_KINDS } from "@/types/chat";

/**
 * Strict canonical block decoder (CHAT-DATA-026 §5).
 *
 * The iOS client never serialises a standalone `kind`; the Web derives it from
 * the payload discriminator, mirroring ``decode_payload`` on the server.  A
 * block type is the single known discriminator key of the `{"<kind>": {"_0":
 * value}}` payload — never a `kind` field and never a default to `text`.
 *
 * The decoded `ChatBlockDTO.payload` keeps the original tagged wire shape
 * (discriminator key **and** `_0` wrapper intact).  Renderers must extract the
 * associated value through :func:`blockAssociatedValue` — a read-only selector,
 * not a second message model.
 */

const KIND_TO_PAYLOAD_KEY = new Map<string, string>(CHAT_BLOCK_KINDS.map((kind) => [kind, kind.replace(/([A-Z])/g, "_$1").toLowerCase()]));
const PAYLOAD_KEY_TO_KIND = new Map<string, string>(Array.from(KIND_TO_PAYLOAD_KEY, ([kind, key]) => [key, kind]));
const KNOWN_PAYLOAD_KEYS = new Set<string>(PAYLOAD_KEY_TO_KIND.keys());

const ANCHOR_TYPES = new Set(["messageStart", "messageEnd", "beforeBlock", "afterBlock", "toolCall"]);
const ANCHOR_VALUE_TYPES = new Set(["beforeBlock", "afterBlock", "toolCall"]);

/** Error layering (§6.2): unknown discriminator vs malformed known payload. */
export type BlockPayloadStatus = "canonical" | "contract_error" | "unsupported";

export interface DecodedBlockPayload {
  /** Canonical kind from the discriminator; empty string when not canonical. */
  kind: string;
  /** Associated value of the canonical payload (with `_0` stripped). */
  value: unknown;
  /** Decode status used to choose the diagnostic copy in the renderer. */
  status: BlockPayloadStatus;
}

/** Return the single known discriminator of a canonical payload, else null. */
export function payloadKind(payload: unknown): string | null {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) return null;
  const obj = payload as Record<string, unknown>;
  const candidates = Object.keys(obj).filter((key) => KNOWN_PAYLOAD_KEYS.has(key));
  if (candidates.length !== 1) return null;
  const wrapper = obj[candidates[0]];
  if (!wrapper || typeof wrapper !== "object" || Array.isArray(wrapper) || !("_0" in wrapper)) return null;
  return PAYLOAD_KEY_TO_KIND.get(candidates[0]) ?? null;
}

/** Strictly decode a wire payload to its kind, associated value and status. */
export function decodeBlockPayload(payload: unknown): DecodedBlockPayload {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    return { kind: "", value: undefined, status: "unsupported" };
  }
  const obj = payload as Record<string, unknown>;
  const candidates = Object.keys(obj).filter((key) => KNOWN_PAYLOAD_KEYS.has(key));
  if (candidates.length === 0) return { kind: "", value: obj, status: "unsupported" };
  if (candidates.length > 1) return { kind: "", value: obj, status: "contract_error" };
  const payloadKey = candidates[0];
  const kind = PAYLOAD_KEY_TO_KIND.get(payloadKey) ?? "";
  const wrapper = obj[payloadKey];
  if (!wrapper || typeof wrapper !== "object" || Array.isArray(wrapper) || !("_0" in wrapper)) {
    return { kind, value: undefined, status: "contract_error" };
  }
  return { kind, value: (wrapper as Record<string, unknown>)._0, status: "canonical" };
}

/** Keep the original tagged wire payload untouched (no deep reshape). */
export function normalizeBlockPayload(payload: unknown): Record<string, unknown> {
  if (payload && typeof payload === "object" && !Array.isArray(payload)) {
    return payload as Record<string, unknown>;
  }
  return {};
}

/** Extract a block's associated value.  Flat text is intentionally not treated
 * as canonical; malformed blocks are rendered by the isolated error card. */
export function blockAssociatedValue(block: Pick<ChatBlockDTO, "kind" | "payload">): unknown {
  const payloadKey = KIND_TO_PAYLOAD_KEY.get(block.kind) ?? block.kind;
  const wrapper = block.payload?.[payloadKey];
  if (wrapper && typeof wrapper === "object" && !Array.isArray(wrapper) && "_0" in wrapper) {
    return (wrapper as Record<string, unknown>)._0;
  }
  return undefined;
}

/** Validate an iOS `ChatBlockAnchor` union; non-conforming anchors are dropped. */
export function normalizeBlockAnchor(raw: unknown): ChatBlockAnchor | null {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return null;
  const anchor = raw as Record<string, unknown>;
  const type = anchor.type;
  if (typeof type !== "string" || !ANCHOR_TYPES.has(type)) return null;
  if (ANCHOR_VALUE_TYPES.has(type)) {
    const value = anchor.value;
    if (typeof value !== "string" || !value) return null;
    return { type, value } as ChatBlockAnchor;
  }
  return { type } as ChatBlockAnchor;
}

function asStatus(value: unknown): ChatBlockDTO["status"] {
  return ["pending", "streaming", "ready", "failed"].includes(String(value)) ? (value as ChatBlockDTO["status"]) : "ready";
}

/** Decode a raw wire block into a typed canonical `ChatBlockDTO`. */
export function normalizeSyncBlock(raw: Record<string, unknown>): ChatBlockDTO {
  const explicitPayload = raw.payload && typeof raw.payload === "object" && !Array.isArray(raw.payload)
    ? raw.payload as Record<string, unknown>
    : {};

  const decoded = decodeBlockPayload(explicitPayload);
  const kind = decoded.status === "canonical" ? decoded.kind : "";

  return {
    id: String(raw.id ?? ""),
    kind,
    status: asStatus(raw.status),
    revision: Number(raw.revision ?? 0),
    order_key: typeof raw.order_key === "number" ? raw.order_key : (typeof raw.order_key === "string" && raw.order_key ? raw.order_key : null),
    tool_call_id: typeof raw.tool_call_id === "string" ? raw.tool_call_id : null,
    parent_tool_call_id: typeof raw.parent_tool_call_id === "string" ? raw.parent_tool_call_id : null,
    parent_block_id: typeof raw.parent_block_id === "string" ? raw.parent_block_id : null,
    node_role: String(raw.node_role ?? "timeline"),
    anchor: normalizeBlockAnchor(raw.anchor),
    payload: normalizeBlockPayload(explicitPayload),
    created_at: typeof raw.created_at === "string" ? raw.created_at : undefined,
    updated_at: typeof raw.updated_at === "string" ? raw.updated_at : undefined,
  };
}
