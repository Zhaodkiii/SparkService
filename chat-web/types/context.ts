export interface ThreadPreferencesDTO {
  revision: number;
  capability: "chat";
  enabled_tools: string[];
  knowledge_bases: string[];
  rejected_ids?: Array<{ id: string; reason: string }>;
  subagent: Record<string, unknown>;
  persona: { custom_text?: string; preset_key?: string };
  llm_selection: { provider_key?: string; model?: string; config_version?: string };
  language: string;
  voice_preferences: Record<string, unknown>;
}

export type HealthResourceType =
  | "medical_case"
  | "health_exam_report"
  | "examination_report"
  | "medication_plan"
  | "member_key_indicator";

export type TurnContextItem =
  | { key: string; kind: "attachment"; fileId: string; title: string; status: "registering" | "ready" | "failed" }
  | { key: string; kind: "health_resource"; resourceType: HealthResourceType; resourceId: string; memberId: number; title: string; status: "ready" | "invalid" };

export interface TurnContextDraft {
  threadId: string | null;
  contextParentMessageId: number | null;
  items: TurnContextItem[];
}

export interface CreateTurnContextInput {
  preferencesRevision: number;
  contextParentMessageId: number | null;
  references: Array<{ type: "health_resource"; resource_type: HealthResourceType; resource_id: string }>;
  attachments: Array<{ file_id: string }>;
}
