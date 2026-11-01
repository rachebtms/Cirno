import { useTranslation } from "react-i18next";
import { useState } from "react";
import { Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";

export function ProjectCreateButton({
  onCreate,
}: {
  onCreate?: (name: string, directory: string) => Promise<void>;
}) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [directory, setDirectory] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <div className="flex h-9 shrink-0 items-center justify-between px-4 pt-1 text-[11px] font-medium leading-4 text-sidebar-muted-foreground">
        <span>{t("features.projects")}</span>
        <DialogTrigger asChild>
          <Button
            size="icon"
            variant="ghost"
            className="h-6 w-6 rounded-md text-sidebar-muted-foreground hover:text-sidebar-foreground"
            aria-label={t("features.createProject")}
          >
            <Plus className="h-3.5 w-3.5" />
          </Button>
        </DialogTrigger>
      </div>
      <DialogContent className="max-w-md">
        <DialogTitle>{t("features.createProject")}</DialogTitle>
        <DialogDescription>
          {t("features.projectDescription")}
        </DialogDescription>
        <form
          className="space-y-4"
          onSubmit={async (event) => {
            event.preventDefault();
            setSaving(true);
            setError("");
            try {
              await onCreate?.(name, directory);
              setOpen(false);
              setName("");
              setDirectory("");
            } catch (reason) {
              setError((reason as Error).message);
            } finally {
              setSaving(false);
            }
          }}
        >
          <label className="block text-sm">
            {t("features.name")}
            <Input
              autoFocus
              required
              value={name}
              onChange={(event) => setName(event.target.value)}
            />
          </label>
          <label className="block text-sm">
            {t("features.defaultDirectory")}
            <Input
              value={directory}
              onChange={(event) => setDirectory(event.target.value)}
            />
          </label>
          {error && (
            <p role="alert" className="text-sm text-destructive">
              {error}
            </p>
          )}
          <Button type="submit" disabled={saving || !name.trim()}>
            {t("features.create")}
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}
