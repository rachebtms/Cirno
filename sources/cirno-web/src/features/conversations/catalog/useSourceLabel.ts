import { useContext } from "react";
import { ConversationCatalogContext } from "./context";
import { ROUTER_SESSION_KEY, routerLabel } from "@/lib/conversation-role";

export function useSourceLabel() {
  const catalog = useContext(ConversationCatalogContext);
  return (key: string) => key === ROUTER_SESSION_KEY ? routerLabel(catalog?.sessions ?? []) : key.replace(/^websocket:/, "@");
}
