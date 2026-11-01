import { useState } from "react";
import { Eraser } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { HoverHint } from "@/components/ui/tooltip";
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from "@/components/ui/alert-dialog";
import type { CirnoClient } from "@/lib/cirno-client";

export function ClearConversationButton({ client, chatId, onCleared }: {
  client: CirnoClient; chatId: string; onCleared: () => void;
}) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function clear() {
    setBusy(true); setError("");
    try {
      await client.sendSystemCommand(chatId, "/new", 30_000);
      onCleared(); setOpen(false);
    } catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
    finally { setBusy(false); }
  }
  return <>
    <HoverHint content={t("thread.clear.title")}><Button type="button" variant="ghost" size="icon"
      className="host-no-drag text-muted-foreground/85 hover:text-foreground" aria-label={t("thread.clear.title")}
      onClick={() => { setError(""); setOpen(true); }}><Eraser className="h-4 w-4" /></Button></HoverHint>
    <AlertDialog open={open} onOpenChange={(value) => { if (!busy) setOpen(value); }}>
      <AlertDialogContent><AlertDialogHeader><AlertDialogTitle>{t("thread.clear.title")}</AlertDialogTitle>
        <AlertDialogDescription>{t("thread.clear.description")}</AlertDialogDescription></AlertDialogHeader>
        {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
        <AlertDialogFooter><AlertDialogCancel disabled={busy}>{t("files.cancel")}</AlertDialogCancel>
          <AlertDialogAction disabled={busy} onClick={(event) => { event.preventDefault(); void clear(); }}>{t("thread.clear.confirm")}</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  </>;
}
