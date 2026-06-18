/** API response types for ForensicAuth backend. */

export interface User {
  id: string;
  username: string;
  email: string;
  role: "admin" | "perito";
  is_active: boolean;
  password_set: boolean;
}

export interface AuthTokens {
  access_token: string;
  token_type: string;
  user?: User;
}

export interface Case {
  id: string;
  protocol_number: string;
  inquiry_number?: string;
  process_number?: string;
  title: string;
  description: string;
  status: "aberto" | "fechamento_pendente" | "fechado";
  storage_mode?: "va" | "peritus";
  created_by: string;
  assigned_to?: string;
  created_at: string;
  updated_at: string;
}

export interface CaseDetail extends Case {
  evidence_count?: number;
  is_shared?: boolean;
}

export interface CaseClosure {
  id: string;
  case_id: string;
  closure_sequence: number;
  manifest_sha256: string;
  signature_mode: string;
  signed_by: string;
  signed_at: string;
  system_signature?: string | null;
}

export interface CreateCaseRequest {
  protocol_number: string;
  inquiry_number?: string;
  process_number?: string;
  title: string;
  description?: string;
  assigned_to?: string;
}

export interface UpdateCaseRequest {
  protocol_number?: string;
  inquiry_number?: string;
  process_number?: string;
  title?: string;
  description?: string;
  status?: "aberto" | "fechamento_pendente" | "fechado";
  assigned_to?: string;
}

export interface Evidence {
  id: string;
  case_id: string;
  filename: string;
  original_filename: string;
  file_size: number;
  file_type: string;
  mime_type: string | null;
  sha256: string;
  extra_metadata: Record<string, unknown>;
  uploaded_by: string;
  created_at: string;
}

export interface AudioTechnicalMetadata {
  evidence_id: string;
  sample_rate_hz: number | null;
  duration_sec: number | null;
  bit_depth: number | null;
  codec: string | null;
  channels: number | null;
}

export interface AnalysisJob {
  id: string;
  evidence_id: string;
  technique: string;
  status: "pending" | "running" | "completed" | "failed";
  parameters: Record<string, unknown>;
  result_path?: string;
  result_sha256?: string;
  created_at: string;
  started_at?: string;
  completed_at?: string;
  error_message?: string;
}

export interface PluginInfo {
  name: string;
  supported_types: string[];
}

export interface JobSubmitRequest {
  evidence_id: string;
  technique: string;
  parameters?: Record<string, unknown>;
}
