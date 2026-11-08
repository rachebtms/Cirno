import { Button, Dropdown, SearchField } from "@heroui/react";
import { Archive, ArrowDownWideNarrow } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { SidebarSortMode } from "@/lib/contracts/conversation-preferences";
import { useConversationCatalog } from "../catalog/context";
import { useActiveMenu } from "@/ui/overlays/useActiveMenu";
const SORTS: SidebarSortMode[] = ["updated_desc", "created_desc", "title_asc", "manual"];
export function CatalogToolbar({ query, onChange, active }: { query: string; onChange: (value: string) => void; active: boolean }) {
  const { t } = useTranslation();
  const catalog = useConversationCatalog();
  const menu = useActiveMenu(active, catalog.owner);
  return <div className="conversation-catalog-toolbar">
    <SearchField aria-label={t("conversationCatalog.search")} value={query} onChange={onChange} className="conversation-search">
      <SearchField.Group><SearchField.SearchIcon /><SearchField.Input placeholder={t("conversationCatalog.search")} /><SearchField.ClearButton /></SearchField.Group>
    </SearchField>
    <Dropdown {...menu}><Button isIconOnly variant="secondary" aria-label={t("conversationCatalog.sort")}><ArrowDownWideNarrow size={18} /></Button>
      <Dropdown.Popover placement="bottom end"><Dropdown.Menu aria-label={t("conversationCatalog.sort")} selectionMode="single"
        selectedKeys={[catalog.preferences?.view?.sort ?? "updated_desc"]}>
        {SORTS.map(key => <Dropdown.Item key={key} id={key} textValue={t(`conversationCatalog.order.${key}`)} onAction={() => catalog.setSort(key)}>{t(`conversationCatalog.order.${key}`)}<Dropdown.ItemIndicator /></Dropdown.Item>)}
        <Dropdown.Section selectionMode="none"><Dropdown.Item id="archived" textValue={t(catalog.showArchived ? "chat.hideArchived" : "chat.showArchived")}
          onAction={catalog.toggleArchived}><Archive size={15} />{t(catalog.showArchived ? "chat.hideArchived" : "chat.showArchived")}</Dropdown.Item></Dropdown.Section>
      </Dropdown.Menu></Dropdown.Popover>
    </Dropdown>
  </div>;
}
