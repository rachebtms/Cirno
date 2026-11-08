import { Alert, Button, Chip, Spinner, Tabs } from "@heroui/react";
import { ArrowLeft, Bell, CheckCheck, Inbox, RefreshCw } from "lucide-react";
import { useTranslation } from "react-i18next";
import { EmptyState, Page, PageHeader } from "@/ui/layout/Page";
import { INBOX_CATEGORIES, type InboxCategory } from "./model/store";
import { useInboxFeed } from "./model/useInboxFeed";
import { NoticeCard } from "./ui/NoticeCard";
import "./inbox.css";
export function InboxPage({ onBack, onSelect, onSettings, returnKey }: {
  onBack: () => void; onSelect: (key: string) => void; onSettings: () => void; returnKey?: string | null;
}) {
  const { t } = useTranslation();
  const feed = useInboxFeed(onSelect, returnKey);
  return <Page label={t("inbox.title")} className="inbox-page">
    <PageHeader title={t("inbox.title")} description={t("inbox.retained")} actions={<>
      <Button isIconOnly variant="ghost" aria-label={t("inbox.back")} onPress={onBack}><ArrowLeft size={18} /></Button>
      <Button isIconOnly variant="ghost" aria-label={t("inbox.settings")} onPress={onSettings}><Bell size={18} /></Button>
    </>} />
    <div className="inbox-toolbar">
      <Tabs selectedKey={feed.category ?? "all"} onSelectionChange={key => feed.selectCategory(String(key))}>
        <Tabs.ListContainer><Tabs.List aria-label={t("inbox.categories")}>
          {["all", ...INBOX_CATEGORIES].map(key => <Tabs.Tab key={key} id={key}>
            {t(`inbox.category.${key}`)}
            {key !== "all" && feed.unread[key as InboxCategory] > 0 && <Chip size="sm" variant="soft">{feed.unread[key as InboxCategory]}</Chip>}
            <Tabs.Indicator />
          </Tabs.Tab>)}
        </Tabs.List></Tabs.ListContainer>
      </Tabs>
      <div className="inbox-toolbar-actions">
        <Button isIconOnly variant="ghost" isDisabled={!!feed.busy} aria-label={t("inbox.refresh")} onPress={() => void feed.refresh()}><RefreshCw size={17} /></Button>
        <Button variant="ghost" size="sm" isDisabled={!!feed.busy} onPress={() => void feed.markAllRead()}><CheckCheck size={16} />{t("inbox.markAllRead")}</Button>
      </div>
    </div>
    {feed.error && <Alert status="danger" role="alert"><Alert.Content><Alert.Description>{feed.error}</Alert.Description></Alert.Content></Alert>}
    {!feed.page && !feed.error && <div className="feature-empty" role="status"><Spinner /><span>{t("inbox.loading")}</span></div>}
    {feed.page?.items.length === 0 && <EmptyState icon={<Inbox />} title={t("inbox.empty")} />}
    <div className="inbox-notices">{feed.page?.items.map(notice => <NoticeCard key={notice.id} notice={notice} feed={feed} />)}</div>
    {feed.page?.next_before && <Button variant="secondary" isDisabled={!!feed.busy} onPress={() => void feed.more()}>{t("inbox.loadMore")}</Button>}
  </Page>;
}
