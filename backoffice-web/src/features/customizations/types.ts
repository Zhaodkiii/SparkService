export type Photo = {
  id: string;
  client_id?: string;
  position: number;
  note: string;
  must_use: boolean;
  crop_allowed: boolean;
  cover_preferred?: boolean;
  status?: string;
  size?: number;
  width?: number;
  height?: number;
  mime?: string;
  sha256?: string;
  available?: boolean;
  removed?: boolean;
  url?: string | null;
  thumbnail_url?: string | null;
  error?: string;
};
export type Submission = {
  id: number;
  number: number;
  created_at: string;
  snapshot: { title: string; brief: Record<string, string>; assets: Photo[] };
  resolved_assets: Photo[];
};
export type Delivery = {
  id: string;
  number: number;
  candidate_number: number;
  published_number: number | null;
  status: string;
  submission_id: number;
  title: string;
  page_count: number;
  photo_slots: number;
  text_slots: number;
  version: number;
  note: string;
  pages: { id: string; title: string; preview_url: string | null }[];
};
export type Job = {
  id: string;
  kind: string;
  status: string;
  error: string;
  submission_id: number;
  created_at: string;
  result?: { delivery_id?: string };
};
export type Row = {
  id: string;
  number: string;
  title: string;
  status: string;
  revision: number;
  owner_id: number;
  owner_name: string;
  assigned_to: number | null;
  assigned_name: string | null;
  updated_at: string;
  due_at: string | null;
  pending_submission: boolean;
  cancellation_requested: boolean;
  overdue: boolean;
};
export type Notice = {
  id: number;
  scene: string;
  status: string;
  seen: boolean;
  created_at: string;
  deliveries: {
    id: number;
    message_id: number;
    status: string;
    error_message: string;
    attempt_count: number;
    provider_status: string;
  }[];
  outbox: {
    status: string;
    last_error: string;
    available_at: string;
    attempts: number;
  }[];
};
export type Detail = Row & {
  brief: Record<string, string>;
  assets: Photo[];
  submissions: Submission[];
  accepted_submission_id: number | null;
  latest_submission_id: number | null;
  current_delivery_id: string | null;
  internal_note: string;
  allowed_actions: string[];
  next_step: string;
  reminder_available_at: string | null;
  deliveries: Delivery[];
  jobs: Job[];
  events: {
    id: string;
    sequence: number;
    action: string;
    message: string;
    created_at: string;
  }[];
  notifications: Notice[];
  audit: {
    id: number;
    action: string;
    actor: string;
    created_at: string;
    details: { message?: string; assigned_to?: number; revision?: number };
  }[];
};
export type Review = { used: string[]; reviewed: boolean; message: string };
export type Editor = {
  submission?: number;
  due: string | null;
  internalNote: string;
  assignedTo?: number;
  reviews: Record<string, Review>;
  previewCandidate?: string;
  section: string;
};
export type ArchiveInfo = {
  sha: string;
  title: string;
  packageVersion: number;
  pageCount: number;
  requestID: string;
};
export type UploadSession = {
  id: string;
  status: string;
  credentials?: {
    accessKeyId: string;
    accessKeySecret: string;
    stsToken: string;
    bucket: string;
    region: string;
    endpoint: string;
    key: string;
  };
};
