import { useRef, useState } from "react";
import { AccountRequestError, accountRequest, validAccountPassword } from "@/lib/account";

export function useAccountEntry(mode: "register" | "login", onSuccess: () => void) {
  const [username, setUsername] = useState("");
  const [routerHandle, setRouterHandle] = useState("cirno");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [visible, setVisible] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<{ code: string; detail?: string } | null>(null);
  const pending = useRef(false);
  const register = mode === "register";
  async function submit() {
    if (pending.current) return;
    const handle = routerHandle.trim().replace(/^@/, "").toLowerCase();
    const invalid = register && !/^[a-z][a-z0-9_]{2,31}$/.test(handle) ? "invalid_router_handle" : !username.trim() ? "invalid_username" : register && !validAccountPassword(password) ? "invalid_password"
      : register && password !== confirm ? "password_mismatch" : !password ? "invalid_credentials" : null;
    if (invalid) { setError({ code: invalid }); return; }
    pending.current = true; setBusy(true); setError(null);
    try {
      await accountRequest(mode, { username: username.trim(), password, ...(register ? { router_handle: handle } : {}) });
      onSuccess();
    } catch (reason) {
      setError(reason instanceof AccountRequestError ? { code: reason.code }
        : { code: "connection_failed", detail: reason instanceof Error ? reason.message : String(reason) });
    } finally { pending.current = false; setBusy(false); }
  }
  return { register, routerHandle, setRouterHandle, username, setUsername, password, setPassword, confirm, setConfirm, visible, setVisible, busy, error, submit };
}
