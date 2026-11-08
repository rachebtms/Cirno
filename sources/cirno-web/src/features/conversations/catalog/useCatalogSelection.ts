import { displayTitle } from "@/lib/chat-groups";
import type { ChatSummary } from "@/lib/contracts/conversations";
import { useMemo, type RefObject } from "react";
import { useTranslation } from "react-i18next";
import { useConversationSelection } from "../shared/useConversationSelection";
import { useConversationCatalog } from "./context";

const EMPTY = new Set<string>();

export function useCatalogSelection(
  rows: ChatSummary[],
  viewport: RefObject<HTMLElement | null>,
) {
  const { t } = useTranslation();
  const catalog = useConversationCatalog();
  const items = useMemo(
    () =>
      new Map(
        rows.map((session) => [
          session.key,
          {
            key: session.key,
            label: displayTitle(
              session,
              catalog.preferences?.title_overrides ?? {},
              t("sidebar.newChat"),
            ),
          },
        ]),
      ),
    [rows, catalog.preferences?.title_overrides, t],
  );
  return useConversationSelection({
    deleteItemsByKey: items,
    selectableDeleteKeys: [...items.keys()],
    archived: new Set(catalog.preferences?.archived_keys ?? []),
    archivedPanes: EMPTY,
    scrollViewportRef: viewport,
    onRequestDelete: catalog.deleteConversation,
    onRequestDeleteMany: catalog.deleteMany,
  });
}
