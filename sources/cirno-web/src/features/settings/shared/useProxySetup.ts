import { useEffect, useRef, useState } from "react";

export function useProxySetup(onSave: (address: string) => Promise<void>, onClose: () => void, busy: boolean) {
  const [address, setAddress] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const input = useRef<HTMLInputElement>(null);
  const pending = busy || saving;
  useEffect(() => { if (error && !pending) input.current?.focus(); }, [error, pending]);
  const save = async () => {
    if (pending || !address.trim()) return;
    setSaving(true);
    setError("");
    try {
      await onSave(address);
      onClose();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setSaving(false);
    }
  };
  return { address, change: (next: string) => { setAddress(next); setError(""); }, pending, error, input, save };
}
