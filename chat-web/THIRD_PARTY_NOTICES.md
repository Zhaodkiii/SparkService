# Third-party notices

## DeepTutor Web

- Source repository: `/Users/hua/Documents/project/DeepTutor/DeepTutorSerevr`
- Source commit: `684d615393322cd18d9edb3a85eacb3beba0d811`
- License: Apache-2.0
- Scope: P0 utility/UI fragments only; Spark API, authentication, session state, provider calls and teaching features are not copied.

| Source | Target | Classification | Modification |
| --- | --- | --- | --- |
| `web/lib/composer-keyboard.ts` | `lib/composer-keyboard.ts` | Direct reuse | Spark Composer limits documented in source comments |
| `web/lib/use-auto-sized-textarea.ts` | `lib/use-auto-sized-textarea.ts` | Direct reuse | Spark 28–200px bounds |
| `web/lib/use-ime-composing.ts` | `lib/use-ime-composing.ts` | Direct reuse | No business imports |
| `web/lib/debounce.ts` | `lib/debounce.ts` | Direct reuse | Browser-safe timer type |
| `web/lib/relative-time.ts` | `lib/relative-time.ts` | Direct reuse | Spark locale wrapper |
| `web/hooks/useLockBodyScroll.ts` | `hooks/useLockBodyScroll.ts` | Direct reuse | Drawer-only usage |
| `web/hooks/useMeasuredHeight.ts` | `hooks/useMeasuredHeight.ts` | Direct reuse | ResizeObserver fallback retained |
| `web/hooks/useChatAutoScroll.ts` | `hooks/useChatAutoScroll.ts` | Partial migration | Pin-to-bottom, MutationObserver and intent-release behavior retained; Spark Run revision/ref semantics adapted |
| `web/components/sidebar/SidebarShell.tsx` | `components/sidebar/SidebarShell.tsx` | Partial migration | 220/60px drawer/collapse interaction retained; Spark Thread/route data replaces DeepTutor session API |
| `web/components/chat/home/ChatMessages.tsx` | `components/chat/home/ChatMessages.tsx` | Partial migration | independent scroll, assistant actions and public activity states retained; Spark blocks/events replace DeepTutor messages |
| `web/components/ui/Button.tsx` | `components/ui/Button.tsx` | Partial migration | Spark tokens and labels |
| `web/components/ui/Tooltip.tsx` | `components/ui/Tooltip.tsx` | Partial migration | Spark tokens and keyboard semantics |
| `web/hooks/useSmoothStreamText.ts` | `hooks/useSmoothStreamText.ts` | Direct reuse | Pure React hook, unchanged reveal-speed math |
| `web/components/chat/home/TracePanels.tsx` (ReasoningMark SVG, ~1829-1853) | `components/chat/turn/marks/ReasoningMark.tsx` | Extracted migration | Only the pure SVG mark extracted; shared `MarkSvg` wrapper split into its own file |
| `web/components/chat/home/TracePanels.tsx` (ToolMark SVG, ~1860-1874) | `components/chat/turn/marks/ToolMark.tsx` | Extracted migration | Only the pure SVG mark extracted |
| `web/components/chat/home/TracePanels.tsx` (RespondingMark SVG, ~1881-1892) | `components/chat/turn/marks/RespondingMark.tsx` | Extracted migration | Only the pure SVG mark extracted |
| `web/components/chat/home/TracePanels.tsx` (RespondedMark SVG, ~1899-1916) | `components/chat/turn/marks/RespondedMark.tsx` | Extracted migration | Only the pure SVG mark extracted |
| `web/components/chat/home/TracePanels.tsx` (status header phase→mark/fold logic) | `components/chat/turn/TurnActivity.tsx` | Migrated | Phase-based mark selection, fold-on-final-answer timing and tightened expandability retained; Spark `TurnActivityViewModel`/allow-listed tool projections replace DeepTutor's `UnifiedChatContext`/raw StreamEvent phase data |
| `web/components/chat/home/TracePanels.tsx` (`describeToolCall` verb/chip pattern, ~156-386) | `components/chat/turn/TurnTraceRow.tsx`, `lib/chat/activity-projection.ts` (`ToolTraceViewModel`) | Migrated | Action-verb + artifact-chip row shape retained; verb/chip vocabulary rebuilt for Spark's 5-tool allowlist, built strictly on the existing desensitized `display_args`/error copy — no raw arguments or DeepTutor tool catalog copied |
| `web/components/common/ModelThinkingCard.tsx` | `components/chat/turn/PublicThinkingCard.tsx` | Migrated | `<details>` expand-while-streaming/auto-collapse/manual-toggle interaction retained; input strictly limited to Spark's existing `extractPublicSummary` (`payload.summary/reasoning_content/text/content`) — the raw `<think>` scratchpad semantics are not introduced |

No DeepTutor API, auth, WebSocket, provider, database, logo, brand asset or teaching feature is included.
