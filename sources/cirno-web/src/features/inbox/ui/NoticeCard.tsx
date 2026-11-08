import { Button, Card, Chip } from "@heroui/react";
import { CircleHelp, ExternalLink, MessageCircle, Settings2, ShieldCheck } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { InboxNotice } from "../model/store";
import type { InboxFeed } from "../model/useInboxFeed";
export function NoticeCard({ notice, feed }: { notice: InboxNotice; feed: InboxFeed }) {
  const { t, i18n } = useTranslation();
  const Icon = notice.kind === "approval" ? ShieldCheck : ({ operations: CircleHelp, conversations: MessageCircle, system: Settings2 })[notice.category];
  const pending = notice.status === "pending";
  const failed = notice.status === "failed";
  return <Card className="inbox-notice" data-unread={!notice.read_at}>
    <Card.Content className="inbox-notice-content">
      <Icon size={18} className="inbox-notice-icon" aria-hidden />
      <div className="inbox-notice-main">
        <div className="inbox-notice-heading"><h2>{t(`inbox.kind.${notice.kind}`, { defaultValue: t(`inbox.category.${notice.category}`) })}</h2>
          <Chip size="sm" variant="soft" color={failed ? "danger" : pending ? "warning" : "default"}>{t(`inbox.status.${notice.status}`, { defaultValue: notice.status })}</Chip>
          {!notice.read_at && <span className="inbox-unread-dot" aria-label={t("inbox.unread")} />}
          <time dateTime={new Date(notice.created_at).toISOString()}>{new Intl.DateTimeFormat(i18n.resolvedLanguage, { dateStyle: "short", timeStyle: "short" }).format(notice.created_at)}</time>
        </div>
        {notice.data.session_title && <p className="inbox-notice-source">{notice.data.session_title}</p>}
        {notice.body && <p className="inbox-notice-text">{notice.body}</p>}
        {notice.kind === "approval" && notice.data.operation && <details className="inbox-operation"><summary>{notice.data.operation}</summary>
          <pre>{JSON.stringify(notice.data.arguments, null, 2)}</pre></details>}
        <div className="inbox-notice-actions">
          {notice.session_key && <Button variant="ghost" size="sm" isDisabled={!!feed.busy || notice.status === "unavailable"} onPress={() => void feed.open(notice)}>
            <ExternalLink size={14} />{t(notice.kind === "question" && pending ? "inbox.answer" : "inbox.openConversation")}</Button>}
          {notice.kind === "approval" && pending && <>
            <Button size="sm" isDisabled={!!feed.busy} onPress={() => void feed.decide(notice, true)}>{t("inbox.approve")}</Button>
            <Button variant="danger-soft" size="sm" isDisabled={!!feed.busy} onPress={() => void feed.decide(notice, false)}>{t("inbox.deny")}</Button>
          </>}
          {!notice.read_at && <Button variant="ghost" size="sm" isDisabled={!!feed.busy} onPress={() => void feed.markRead(notice)}>{t("inbox.markRead")}</Button>}
        </div>
      </div>
    </Card.Content>
  </Card>;
}
