import type { PromptHistoryNavigation } from "@/hooks/usePromptHistory";
import type { ThreadMotionCoordinator } from "../thread-motion";
import type { ThreadHistorySpring } from "../thread-history-spring";
import type { HistoryScrollAnchor } from "./geometry";

interface RefCell<T> { current: T; }

export interface ThreadViewportInputOptions {
  motion: ThreadMotionCoordinator;
  spring: ThreadHistorySpring;
  anchor: RefCell<HistoryScrollAnchor | null>;
  pendingInitialScroll: RefCell<boolean>;
  messageContent: RefCell<HTMLDivElement | null>;
  messagesLength: number;
  conversationReady: boolean;
  loadingOlder: boolean;
  hiddenMessageCount: number;
  hasMoreBefore: boolean;
  olderError: string | null;
  historySlotKey: string | null;
  historyWindow: PromptHistoryNavigation["window"] | undefined;
  navigation: PromptHistoryNavigation | undefined;
  setAtBottom: (value: boolean) => void;
  setAtHistoryTop: (value: boolean) => void;
  captureHistoryScrollAnchor: () => boolean;
  maybeLoadEarlierFromScroll: () => void;
  loadEarlierMessages: () => void;
  yieldCameraToUser: () => void;
  resetHistoryHeader: () => void;
}
