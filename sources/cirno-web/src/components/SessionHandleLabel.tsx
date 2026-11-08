import { useContext, type ReactNode } from "react";
import { ConversationCatalogContext } from "@/features/conversations/catalog/context";

import { InlineTokenHighlight } from "@/components/InlineTokenHighlight";
import { sessionHandleColor } from "@/lib/session-handle";

export function SessionHandleLabel({
  id,
  children,
}: {
  id: string;
  children: ReactNode;
}) {
  const catalog = useContext(ConversationCatalogContext);
  const current = catalog?.sessions.find(session => session.handle?.id === id)?.handle;
  return (
    <InlineTokenHighlight
      color={sessionHandleColor(id)}
    >
      {current ? `@${current.name}` : children}
    </InlineTokenHighlight>
  );
}
