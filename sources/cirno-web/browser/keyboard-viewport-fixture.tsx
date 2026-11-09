import { useAppViewport } from "@/hooks/useAppViewport";
import { EntryFixture } from "./entry-fixture";
import { MobileChatLayoutFixture } from "./mobile-chat-layout-fixture";

export function KeyboardViewportFixture({ parameters }: { parameters: URLSearchParams }) {
  useAppViewport();
  return parameters.get("surface") === "chat"
    ? <MobileChatLayoutFixture parameters={parameters} />
    : <EntryFixture />;
}
