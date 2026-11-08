import { Button } from "@heroui/react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { ChatSummary } from "@/lib/contracts/conversations";
import type { ConversationSelection } from "../shared/useConversationSelection";
import { ConversationRow } from "./ConversationRow";

export function ConversationList({ rows, selection, active }: { rows: ChatSummary[]; selection: ConversationSelection; active: boolean }) {
  const { t } = useTranslation();
  const [limit, setLimit] = useState(30);
  return <>{rows.slice(0, limit).map(session => <ConversationRow key={session.key} session={session} selection={selection} active={active} />)}
    {rows.length > limit && <Button variant="ghost" onPress={() => setLimit(count => count + 30)}>{t("conversationCatalog.more")}</Button>}</>;
}
