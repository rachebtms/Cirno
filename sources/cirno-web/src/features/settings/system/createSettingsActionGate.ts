interface MutableValue<T> { current: T }

export interface SettingsResourceOwner {
  isCurrent: () => boolean;
  actionRef: MutableValue<string | null>;
  revisionRef: MutableValue<number>;
}

interface SettingsActionGateOptions extends SettingsResourceOwner {
  setAction: (key: string | null) => void;
  setLoading: (loading: boolean) => void;
  isBlocked?: () => boolean;
}

/** Admit one settings write and fence reads on both sides of its settlement. */
export function createSettingsActionGate({
  isCurrent, actionRef, revisionRef, setAction, setLoading, isBlocked,
}: SettingsActionGateOptions) {
  return {
    begin(key: string): boolean {
      if (!isCurrent() || actionRef.current || isBlocked?.()) return false;
      actionRef.current = key;
      revisionRef.current += 1;
      setAction(key);
      setLoading(false);
      return true;
    },
    end(key: string): void {
      if (!isCurrent() || actionRef.current !== key) return;
      revisionRef.current += 1;
      actionRef.current = null;
      setAction(null);
    },
  };
}
