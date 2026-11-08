import { Button, Popover } from "@heroui/react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { InlineError } from "@/ui/feedback/InlineError";
import { useRequest } from "@/ui/resources/useRequest";
import type { MemoryService } from "../model/service";
export function TagBrowser({
  service,
  onSelect,
}: {
  service: MemoryService;
  onSelect: (tag: string) => void;
}) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const state = useRequest<{ tags: { name: string; count: number }[] }>(service);
  const { load } = state;
  useEffect(() => {
    if (open) void load(() => service.tags());
  }, [open, service, load]);
  return (
    <Popover isOpen={open} onOpenChange={setOpen}>
      <Button variant="secondary" size="sm">
        {t("memoryLibrary.discoverTags")}
      </Button>
      <Popover.Content>
        <Popover.Dialog className="memory-tags-dialog" aria-label={t("memoryLibrary.discoverTags")}>
          <Popover.Heading>{t("memoryLibrary.discoverTags")}</Popover.Heading>
          <InlineError message={state.error} />
          {state.loading && (
            <p role="status" className="memory-hint">
              {t("settings.loading")}
            </p>
          )}
          {state.error && (
            <Button
              variant="ghost"
              size="sm"
              onPress={() => {
                void load(() => service.tags());
              }}
            >
              {t("common.retry")}
            </Button>
          )}
          <div className="memory-tag-options">
            {state.value?.tags.map((tag) => (
              <Button
                variant="ghost"
                size="sm"
                key={tag.name}
                onPress={() => {
                  onSelect(tag.name);
                  setOpen(false);
                }}
              >
                {tag.name} · {tag.count}
              </Button>
            ))}
          </div>
          {state.status === "success" && !state.value?.tags.length && (
            <p className="memory-hint">{t("memoryLibrary.noTags")}</p>
          )}
        </Popover.Dialog>
      </Popover.Content>
    </Popover>
  );
}
