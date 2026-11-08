import { useTheme } from "@/hooks/useTheme";
import { AccountSettings } from "@/features/settings/account/AccountSettings";
import { useState } from "react";
import { AccountEntry } from "@/features/entry/AccountEntry";
import { AccessEntry } from "@/features/entry/AccessEntry";

export function EntryFixture() {
  useTheme();
  const [complete, setComplete] = useState(false);
  const mode = new URLSearchParams(location.search).get("mode");
  if (mode === "settings") return <main style={{ padding: "1.5rem", maxWidth: "44rem", margin: "auto" }}><AccountSettings /></main>;
  if (complete) return <h1>Account ready</h1>;
  return mode === "access" ? <AccessEntry failed={false} onSecret={() => setComplete(true)} />
    : <AccountEntry mode={mode === "login" ? "login" : "register"} onSuccess={() => setComplete(true)} />;
}
