export type InteractionKind = "ask_user" | "client_tool" | "consent";

export type InteractionStatus =
  | "pending"
  | "claimed"
  | "resolved"
  | "refused"
  | "expired"
  | "cancelled";

export interface InteractionQuestionOption {
  label: string;
  description?: string | null;
}

export interface InteractionQuestion {
  id: string;
  header?: string | null;
  prompt: string;
  options?: InteractionQuestionOption[];
  multi_select?: boolean;
  allow_free_text?: boolean;
  placeholder?: string | null;
}

export interface PendingInteractionRequest {
  intro?: string | null;
  questions?: InteractionQuestion[];
}

export interface InteractionAnswerDTO {
  question_id: string;
  selected_option_indexes: number[];
  selected_labels: string[];
  free_text?: string;
  has_free_text?: boolean;
}

export interface PendingInteractionDTO {
  run_id: string;
  interaction_id: string;
  interaction_key: string;
  kind: InteractionKind | string;
  status: InteractionStatus | string;
  tool_call_id: string | null;
  tool_name?: string;
  tool_version?: string;
  schema_version: number;
  question_ids: string[];
  request: PendingInteractionRequest;
  expires_at: string | null;
  required_platform?: string;
  required_capability?: string;
  claim_expires_at?: string | null;
  result_summary?: string;
  error_code?: string;
}

export interface InteractionSubmitBody {
  run_id: string;
  interaction_key: string;
  schema_version: number;
  resolution?: "answered" | "skipped" | "refused";
  question_ids?: string[];
  answers?: InteractionAnswerDTO[];
  reason?: string;
}

export interface InteractionCommandData {
  interaction: PendingInteractionDTO;
  run: {
    id: string;
    thread_id?: string;
    status: string;
    last_sequence?: number;
  };
  accepted?: boolean;
  replayed?: boolean;
}

export const INTERACTION_EVENT_TYPES = [
  "interaction.requested",
  "interaction.resolved",
  "interaction.refused",
  "interaction.expired",
  "interaction.cancelled",
  "interaction.claimed",
] as const;

export function isInteractionEventType(type: string): boolean {
  return (INTERACTION_EVENT_TYPES as readonly string[]).includes(type);
}

export function isOpenInteractionStatus(status: string | undefined | null): boolean {
  return status === "pending" || status === "claimed";
}
