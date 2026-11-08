export interface NodeRecord {
  id: string; name: string; host: string; port: number; username: string;
  auth_method: "key" | "password"; has_password?: boolean; agent_visible?: boolean;
  identity_file: string; working_directory: string; host_key: string;
}
export interface NodeDraft { id?: string; credential_id: string; working_directory: string }
export interface NodeJob { id: string; node_id: string; state: string; command: string; output?: string; error?: string }
export function nodeDraft(node?: NodeRecord): NodeDraft {
  return { id: node?.id, credential_id: node?.id ?? "", working_directory: node?.working_directory ?? "." };
}
export const validPort = (value: string) => /^\d+$/.test(value) && Number(value) >= 1 && Number(value) <= 65535;
