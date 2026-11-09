import type { SSHSessionDraft, SSHSessionValues } from "@/components/ssh/session";
export const credentialKinds = ["password", "text", "identity", "token", "ssh"] as const;
export type CredentialKind = typeof credentialKinds[number];
export interface CredentialInfo { id: string; label: string; kind: CredentialKind; agent_visible?: boolean; node_enabled?: boolean }
export interface SSHFields {
  host: string; port: string; username: string; auth_method: "key" | "password";
  password: string; identity_file: string; host_key: string; has_password?: boolean;
}
export const emptySSH = (): SSHFields => ({ host: "", port: "22", username: "", auth_method: "key", password: "", identity_file: "", host_key: "" });
export interface SSHResponse extends Omit<SSHFields, "port">, SSHSessionValues { port: number; node_enabled: boolean }
export interface CredentialDraft {
  id?: string; label: string; kind: CredentialKind; username: string; value: string; modified: boolean; agentVisible: boolean;
  ssh: SSHFields; sshLoaded: boolean; nodeEnabled: boolean; session: SSHSessionDraft;
}
export type CredentialPatch = Partial<Pick<CredentialDraft, "agentVisible" | "label" | "kind" | "username" | "value" | "ssh" | "nodeEnabled" | "session">>;
