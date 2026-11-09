export interface EnvironmentEntry { id: string; name: string; value: string }
export interface SSHSessionDraft { working_directory: string; init_script: string; environment: EnvironmentEntry[] }
export interface SSHSessionValues { working_directory: string; init_script?: string; environment?: Record<string, string> }

export function sshSessionDraft(values?: SSHSessionValues): SSHSessionDraft {
  return { working_directory: values?.working_directory ?? ".", init_script: values?.init_script ?? "",
    environment: Object.entries(values?.environment ?? {}).map(([name, value]) => ({ id: crypto.randomUUID(), name, value })) };
}

export function sshSessionValues(draft: SSHSessionDraft): SSHSessionValues {
  const environment = new Map<string, string>();
  for (const entry of draft.environment) {
    const name = entry.name.trim();
    if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(name) || environment.has(name)) {
      throw new Error("Environment variable names must be valid and unique.");
    }
    environment.set(name, entry.value);
  }
  return { working_directory: draft.working_directory, init_script: draft.init_script, environment: Object.fromEntries(environment) };
}
