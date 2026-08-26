/**
 * P4 web feature flags. Both default to off; the chat must degrade to the
 * plain-text loop (no tool cards, no settings entry) when disabled, without
 * affecting run creation, text streaming or message sync.
 */
export const CHAT_TOOL_UI_ENABLED = process.env.NEXT_PUBLIC_CHAT_TOOL_UI_ENABLED === "1";

export const CHAT_TOOL_SETTINGS_ENABLED = process.env.NEXT_PUBLIC_CHAT_TOOL_SETTINGS_ENABLED === "1";

/**
 * CHAT-WEB-027 W2/W3. Both default to off; disabled state must fall back to
 * the pre-existing renderer (full-text paint / Sparkles-only Activity header)
 * without affecting run creation, text streaming or message sync.
 */
export const CHAT_SMOOTH_STREAM_ENABLED = process.env.NEXT_PUBLIC_CHAT_SMOOTH_STREAM_ENABLED === "1";

export const CHAT_DEEPTUTOR_TURN_UI_ENABLED = process.env.NEXT_PUBLIC_CHAT_DEEPTUTOR_TURN_UI_ENABLED === "1";
