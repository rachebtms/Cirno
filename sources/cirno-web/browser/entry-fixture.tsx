import { SettingsLayout } from "@/features/settings/ui/SettingsLayout";
import { useTheme } from "@/hooks/useTheme";
import { AccountSettings } from "@/features/settings/account/AccountSettings";
import { useState } from "react";
import { AccountEntry } from "@/features/entry/AccountEntry";
import { AccessEntry } from "@/features/entry/AccessEntry";

export function EntryFixture() {
  useTheme();
  const [complete, setComplete] = useState(false);
  const mode = new URLSearchParams(location.search).get("mode");
  if (mode === "settings") return <main style={{ height: "100dvh", display: "flex" }}><SettingsLayout section="account" title="Account" navigation={<aside style={{ width: "15rem", flexShrink: 0 }} aria-label="Settings navigation" />}><AccountSettings /></SettingsLayout></main>;
  if (complete) return <h1>Account ready</h1>;
  return mode === "access" ? <AccessEntry failed={false} onSecret={() => setComplete(true)} />
    : <AccountEntry mode={mode === "login" ? "login" : "register"} onSuccess={() => setComplete(true)} />;
}
