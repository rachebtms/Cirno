import { useState } from "react";
import { useTranslation } from "react-i18next";
export function useBrowserLocation() {
  const { t } = useTranslation();
  const [address, setAddress] = useState("");
  const [url, setUrl] = useState("");
  const [revision, setRevision] = useState(0);
  const [error, setError] = useState("");
  const navigate = () => {
    let parsed: URL;
    try { parsed = new URL(address.includes("://") ? address.trim() : `https://${address.trim()}`); }
    catch { setError(t("workspace.invalidUrl")); return; }
    if (!["http:", "https:"].includes(parsed.protocol)) { setError(t("workspace.invalidUrl")); return; }
    if (parsed.origin === location.origin) { setError(t("workspace.browserSameOrigin")); return; }
    setUrl(parsed.href); setAddress(parsed.href); setError("");
  };
  return { address, setAddress, url, revision, error, navigate, refresh: () => setRevision(value => value + 1) };
}
