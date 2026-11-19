import { useEffect, useRef, useState } from "react";
import { useMutation } from "@/ui/resources/useMutation";

export function useProxySetup(onSave: (address: string) => Promise<void>, onClose: () => void, busy: boolean) {
  const [address, setAddress] = useState("");
  const mutation = useMutation(undefined);
  const error = mutation.error ?? "";
  const input = useRef<HTMLInputElement>(null);
  const pending = busy || mutation.busy;
  useEffect(() => { if (error && !pending) input.current?.focus(); }, [error, pending]);
  const save = async () => {
    if (pending || !address.trim()) return;
    await mutation.run(() => onSave(address), onClose);
  };
  return { address, change: (next: string) => { setAddress(next); mutation.clear(); }, pending, error, input, save };
}
