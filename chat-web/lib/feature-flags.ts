/**
 * P4 web feature flags. Disabled chat must degrade to the plain-text loop
 * (no tool cards, no settings entry) without affecting run creation, text
 * streaming or message sync.
 */
export const CHAT_TOOL_UI_ENABLED = process.env.NEXT_PUBLIC_CHAT_TOOL_UI_ENABLED === "1";

export const CHAT_TOOL_SETTINGS_ENABLED = process.env.NEXT_PUBLIC_CHAT_TOOL_SETTINGS_ENABLED === "1";

/**
 * CHAT-WEB-027 W2. Disabled state falls back to full-text paint without
 * affecting run creation, text streaming or message sync.
 */
export const CHAT_SMOOTH_STREAM_ENABLED = process.env.NEXT_PUBLIC_CHAT_SMOOTH_STREAM_ENABLED === "1";

export const KNOWLEDGE_CENTER_WEB_ENABLED = process.env.NEXT_PUBLIC_KNOWLEDGE_CENTER_WEB_ENABLED !== "0";

export const KNOWLEDGE_CHAT_SELECTOR_ENABLED = process.env.NEXT_PUBLIC_KNOWLEDGE_CHAT_SELECTOR_ENABLED !== "0";
