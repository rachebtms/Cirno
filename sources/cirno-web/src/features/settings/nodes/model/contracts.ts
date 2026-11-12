import { sshSessionDraft, type SSHSessionDraft, type SSHSessionValues } from "@/components/ssh/session";
export interface NodeRecord extends SSHSessionValues {
  id: string; name: string; host: string; port: number; username: string;
  auth_method: "key" | "password"; has_password?: boolean; agent_visible?: boolean;
  identity_file: string; working_directory: string; host_key: string;
}
export interface NodeDraft extends SSHSessionDraft { id?: string; credential_id: string }
export interface NodeJobSettings { poll_interval_seconds: number; retention_days: number }
export const DEFAULT_NODE_JOB_SETTINGS: NodeJobSettings = { poll_interval_seconds: 60, retention_days: 30 };
export interface NodeJob { id: string; node_id: string; state: string; command: string; output?: string; error?: string; submission_error?: string; verification_error?: string; check_error?: string; checked_at?: string; finished_at?: string; created_at?: string; exit_code?: number }
export function nodeDraft(node?: NodeRecord): NodeDraft {
  return { id: node?.id, credential_id: node?.id ?? "", ...sshSessionDraft(node) };
}
export const validPort = (value: string) => /^\d+$/.test(value) && Number(value) >= 1 && Number(value) <= 65535;
