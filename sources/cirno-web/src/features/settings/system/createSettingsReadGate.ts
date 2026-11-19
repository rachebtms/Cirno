import type { SettingsResourceOwner } from "./createSettingsActionGate";

interface SettingsReadGateOptions extends SettingsResourceOwner {
  getToken: () => string;
}

/** Reads share the mutation revision and publish only for their original account. */
export function createSettingsReadGate({
  isCurrent, actionRef, revisionRef, getToken,
}: SettingsReadGateOptions) {
  return () => {
    if (!isCurrent() || actionRef.current) return null;
    const token = getToken();
    const revision = ++revisionRef.current;
    const isLatest = () => isCurrent() && revisionRef.current === revision;
    return {
      token,
      isLatest,
      isCurrent: () => isLatest() && !actionRef.current && token === getToken(),
    };
  };
}
