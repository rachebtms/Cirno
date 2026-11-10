import { Button } from "@heroui/react";
import { Brain } from "lucide-react";
import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import type { WebUIMutationTransport } from "@/lib/api";
import { useWorkspaceOpen } from "@/features/workbench/context";
import { createMemoryService } from "./model/service";
import { MemoryIndexStatus } from "./ui/MemoryIndexStatus";
import "./memory.css";

export function MemorySettings({ client }: { client: WebUIMutationTransport }) {
  const { t } = useTranslation();
  const open = useWorkspaceOpen();
  const service = useMemo(() => createMemoryService(client), [client]);
  return <section className="memory-library">
    <p className="memory-hint">{t("memoryGraph.settingsHelp")}</p>
    {open && <Button variant="secondary" className="memory-open-button" onPress={() => open("memory", { sessionKey: null })}>
      <Brain size={18} />{t("memoryGraph.open")}
    </Button>}
    <MemoryIndexStatus service={service} />
  </section>;
}
