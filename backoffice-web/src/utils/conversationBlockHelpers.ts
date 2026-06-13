import type { ConversationBlock } from '../api/modules/conversations';

const KIND_ALIASES: Record<string, string> = {
  deep_thought: 'deepThought',
  translated_text: 'translatedText',
  image_gallery: 'imageGallery',
  file_attachments: 'fileAttachments',
  knowledge_cards: 'knowledgeCards',
  map_route: 'mapRoute',
  health_cards: 'healthCards',
  pending_member_tool_cards: 'pendingMemberToolCards',
  structured_health_cards: 'structuredHealthCards',
  sleep_visualization: 'sleepVisualization',
  nutrition_cards: 'nutritionCards',
  workout_visualization: 'workoutVisualization',
  capture_card: 'captureCard',
  small_task_card: 'smallTaskCard',
  task_cards: 'taskCards',
  assistant_status_card: 'assistantStatusCard',
  health_resource_reference: 'healthResourceReference',
  medical_risk_notice: 'medicalRiskNotice',
  medical_disclaimer_card: 'medicalDisclaimerCard',
};

export interface ResolvedBlockPresentation {
  kind: string;
  payload: Record<string, unknown>;
}

function asRecord(value: unknown): Record<string, unknown> {
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    return value as Record<string, unknown>;
  }
  return {};
}

export function blockDebugData(block: ConversationBlock) {
  return {
    id: block.id,
    kind: block.kind,
    resolved_kind: block.resolved_kind,
    resolved: block.payload ? resolveBlockPresentation(block) : null,
    status: block.status,
    revision: block.revision,
    order_key: block.order_key,
    tool_call_id: block.tool_call_id,
    parent_tool_call_id: block.parent_tool_call_id,
    parent_block_id: block.parent_block_id,
    node_role: block.node_role,
    anchor: block.anchor,
    payload: block.payload,
    block_summary: block.block_summary,
    has_heavy_detail: block.has_heavy_detail,
    detail_load_mode: block.detail_load_mode,
    detail_endpoint: block.detail_endpoint,
    detail_status: block.detail_status,
    created_at: block.created_at,
    updated_at: block.updated_at,
    is_virtual: block.is_virtual ?? false,
  };
}

export function normalizeBlockKind(rawKind: string): string {
  if (KIND_ALIASES[rawKind]) {
    return KIND_ALIASES[rawKind];
  }
  return rawKind.replace(/_([a-z])/g, (_, char: string) => char.toUpperCase());
}

export function unwrapSwiftEnumValue(value: unknown): unknown {
  if (value && typeof value === 'object' && !Array.isArray(value) && '_0' in (value as Record<string, unknown>)) {
    return (value as Record<string, unknown>)._0;
  }
  return value;
}

function readNestedEnumPayload(payload: Record<string, unknown>): ResolvedBlockPresentation | null {
  const nested = payload.payload;
  if (!nested || typeof nested !== 'object' || Array.isArray(nested)) {
    return null;
  }

  const entries = Object.entries(nested as Record<string, unknown>);
  if (entries.length !== 1) {
    return null;
  }

  const [rawKind, rawValue] = entries[0];
  const kind = normalizeBlockKind(rawKind);
  const unwrapped = unwrapSwiftEnumValue(rawValue);

  if (kind === 'text' || kind === 'translatedText' || kind === 'html' || kind === 'error') {
    const text = typeof unwrapped === 'string' ? unwrapped : readPayloadText(asRecord(unwrapped));
    return { kind, payload: { ...payload, text } };
  }

  if (kind === 'deepThought') {
    const card = asRecord(unwrapped);
    return {
      kind,
      payload: {
        ...payload,
        reasoningContent: card.reasoningContent ?? card.reasoning_content,
        reasoningDurationMs: card.reasoningDurationMs ?? card.reasoning_duration_ms,
        reasoningExpanded: card.reasoningExpanded ?? card.reasoning_expanded,
        reasoningVisibility: card.reasoningVisibility ?? card.reasoning_visibility,
      },
    };
  }

  if (kind === 'tool') {
    const tool = asRecord(unwrapped);
    return { kind, payload: { ...payload, ...tool } };
  }

  if (kind === 'assistantStatusCard') {
    const card = asRecord(unwrapped);
    return { kind, payload: { ...payload, ...card } };
  }

  if (kind === 'imageGallery' || kind === 'fileAttachments') {
    const attachments = Array.isArray(unwrapped) ? unwrapped : payload.attachments;
    return { kind, payload: { ...payload, attachments: attachments || [] } };
  }

  if (Array.isArray(unwrapped)) {
    return { kind, payload: { ...payload, cards: unwrapped } };
  }

  if (unwrapped && typeof unwrapped === 'object') {
    return { kind, payload: { ...payload, ...(unwrapped as Record<string, unknown>) } };
  }

  if (typeof unwrapped === 'string') {
    return { kind, payload: { ...payload, text: unwrapped } };
  }

  return { kind, payload };
}

export function resolveBlockPresentation(block: ConversationBlock): ResolvedBlockPresentation {
  const outer = asRecord(block.payload);
  const nested = readNestedEnumPayload(outer);
  if (nested) {
    return nested;
  }
  return {
    kind: normalizeBlockKind(block.resolved_kind || block.kind || String(outer.kind || 'unknown')),
    payload: outer,
  };
}

export function blockNeedsLazyDetail(block: ConversationBlock): boolean {
  if (block.has_heavy_detail) {
    return block.detail_load_mode === 'lazy' && block.detail_status !== 'loaded' && !block.payload;
  }
  return false;
}

export function readPayloadText(payload: Record<string, unknown>): string {
  for (const key of ['text', 'message', 'content']) {
    const value = payload[key];
    if (typeof value === 'string' && value.trim()) {
      return value.trim();
    }
  }

  const nested = readNestedEnumPayload(payload);
  if (nested && (nested.kind === 'text' || nested.kind === 'translatedText' || nested.kind === 'html' || nested.kind === 'error')) {
    return readPayloadText(nested.payload);
  }

  return '';
}

export function readReasoning(payload: Record<string, unknown>) {
  const nested = readNestedEnumPayload(payload);
  const source = nested?.kind === 'deepThought' ? nested.payload : payload;
  const text = source.reasoningContent ?? source.reasoning_content;
  const ms = source.reasoningDurationMs ?? source.reasoning_duration_ms;
  return {
    text: typeof text === 'string' ? text : '',
    durationMs: typeof ms === 'number' ? ms : null,
  };
}

export function formatDurationMs(ms: number | null): string | null {
  if (!ms || ms <= 0) return null;
  const seconds = ms / 1000;
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const minutes = Math.floor(seconds / 60);
  const remain = seconds % 60;
  return `${minutes}m ${remain.toFixed(1)}s`;
}

export function readTool(payload: Record<string, unknown>) {
  const nested = readNestedEnumPayload(payload);
  const source = nested?.kind === 'tool' ? nested.payload : payload;
  const name = String(source.name || source.toolName || source.tool_name || '工具调用');
  const content = source.content ?? source.result ?? source.output ?? source.response;
  const args = source.arguments ?? source.args ?? source.input ?? source.parameters ?? source.invocationArguments ?? source.invocation_arguments;
  return { name, content, args };
}

export function readAttachments(payload: Record<string, unknown>) {
  const nested = readNestedEnumPayload(payload);
  const source = nested?.payload || payload;
  const raw = source.attachments || source.images || [];
  if (!Array.isArray(raw)) return [];
  return raw.map((item, index) => {
    const record = (item || {}) as Record<string, unknown>;
    const url = ['url', 'remoteURL', 'remoteUrl', 'previewURL', 'previewUrl', 'thumbnailURL', 'thumbnailUrl']
      .map((key) => record[key])
      .find((value) => typeof value === 'string' && value.trim()) as string | undefined;
    return {
      id: String(record.id || index),
      name: String(record.name || record.fileName || record.filename || `附件 ${index + 1}`),
      mime: String(record.mimeType || record.mime_type || record.type || ''),
      size: record.size ? String(record.size) : '',
      url: url || '',
      raw: record,
    };
  });
}

export function readCards(payload: Record<string, unknown>): Record<string, unknown>[] {
  const nested = readNestedEnumPayload(payload);
  const source = nested?.payload || payload;
  const candidates = [source.cards, source.items, source.healthCards, source.structuredCards, payload.cards, payload.items];
  for (const candidate of candidates) {
    if (Array.isArray(candidate)) {
      return candidate.filter((item) => item && typeof item === 'object') as Record<string, unknown>[];
    }
  }
  if (source.blob && typeof source.blob === 'object') {
    const blob = source.blob as Record<string, unknown>;
    if (Array.isArray(blob.cards)) {
      return blob.cards.filter((item) => item && typeof item === 'object') as Record<string, unknown>[];
    }
  }
  return [];
}

export function blockHasVisibleContent(block: ConversationBlock): boolean {
  if (block.has_heavy_detail && !block.payload) {
    return Boolean(block.block_summary?.trim());
  }
  const { kind, payload } = resolveBlockPresentation(block);
  if (!payload) {
    return Boolean(block.block_summary?.trim());
  }
  if (kind === 'text' || kind === 'translatedText' || kind === 'html') {
    return readPayloadText(payload).length > 0;
  }
  if (kind === 'deepThought') {
    return readReasoning(payload).text.length > 0;
  }
  if (kind === 'tool') {
    const tool = readTool(payload);
    return Boolean(tool.name || tool.content || tool.args);
  }
  if (kind === 'imageGallery' || kind === 'fileAttachments') {
    return readAttachments(payload).length > 0;
  }
  if (kind === 'error' || kind === 'assistantStatusCard') {
    return readPayloadText(payload).length > 0 || Boolean(payload.message);
  }
  return true;
}

export function roleLabel(role: string): string {
  if (role === 'user') return '用户';
  if (role === 'assistant') return '助手';
  if (role === 'system') return '系统';
  return role;
}

export function deliveryStateLabel(state: string): string | null {
  if (state === 'sent' || state === 'read') return null;
  if (state === 'pending') return '等待发送';
  if (state === 'sending') return '发送中';
  if (state === 'failed') return '发送失败';
  return state;
}

export function pickCardTitle(card: Record<string, unknown>, fallback: string): string {
  for (const key of ['title', 'mealName', 'meal_name', 'name', 'displayTitle', 'display_title', 'label']) {
    const value = card[key];
    if (typeof value === 'string' && value.trim()) return value.trim();
  }
  return fallback;
}

export function pickCardLines(card: Record<string, unknown>, keys: string[]): Array<{ label: string; value: string }> {
  const lines: Array<{ label: string; value: string }> = [];
  for (const key of keys) {
    const value = card[key];
    if (value === null || value === undefined || value === '') continue;
    if (typeof value === 'object') continue;
    lines.push({ label: key, value: String(value) });
  }
  return lines;
}

export function nutrientItems(card: Record<string, unknown>) {
  const mapping: Array<[string, string, string]> = [
    ['carbohydratesGrams', '碳水化合物', 'g'],
    ['carbohydrates_grams', '碳水化合物', 'g'],
    ['fatGrams', '脂肪', 'g'],
    ['fat_grams', '脂肪', 'g'],
    ['proteinGrams', '蛋白质', 'g'],
    ['protein_grams', '蛋白质', 'g'],
    ['caloriesKcal', '热量', 'kcal'],
    ['calories_kcal', '热量', 'kcal'],
    ['fiberGrams', '膳食纤维', 'g'],
    ['fiber_grams', '膳食纤维', 'g'],
  ];
  return mapping
    .map(([key, label, unit]) => {
      const value = card[key];
      if (typeof value !== 'number') return null;
      return { label, value: `${value}${unit}` };
    })
    .filter(Boolean) as Array<{ label: string; value: string }>;
}

export function medicalNotice(payload: Record<string, unknown>) {
  const nested = readNestedEnumPayload(payload);
  const source = nested?.payload || payload;
  return {
    title: String(source.displayTitle || source.display_title || source.title || '医疗风险提示'),
    message: String(source.displayMessage || source.display_message || source.message || ''),
    riskLevel: String(source.riskLevel || source.risk_level || 'medium'),
    recommendedAction: String(source.recommendedAction || source.recommended_action || ''),
  };
}
