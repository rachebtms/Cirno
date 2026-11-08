import type { ComponentProps, CSSProperties, ReactNode, RefObject } from "react";
import { ArrowDown } from "lucide-react";
import { useTranslation } from "react-i18next";
import { DiagramScope } from "@/components/markdown-diagrams/context";
import { PromptRail } from "../PromptRail";
import { SubagentThreadMessages } from "../SubagentTaskResults";
import { HISTORY_HOLD_PX } from "../thread-history-spring";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { PromptHistoryNavigation } from "@/hooks/usePromptHistory";
import type { UIMessage } from "@/lib/contracts/messages";

interface ViewportSurfaceProps {
  nodes: {
    viewportFrameRef: RefObject<HTMLDivElement | null>; contentRef: RefObject<HTMLDivElement | null>;
    messageContentRef: RefObject<HTMLDivElement | null>; emptyStateRef: RefObject<HTMLDivElement | null>;
    composerDockRef: RefObject<HTMLDivElement | null>; bottomRef: RefObject<HTMLDivElement | null>;
    scrollRef: RefObject<HTMLDivElement | null>
   };
  setMessageRegion: (element: HTMLDivElement | null) => void;
  setHistorySlot: (element: HTMLDivElement | null) => void;
  hasMessages: boolean;
  hasThreadLayout: boolean;
  hasComposer: boolean;
  hasVerticalOverflow: boolean;
  scrollViewportStyle: CSSProperties | undefined;
  composer: ReactNode;
  emptyState: ReactNode;
  initialLoading: boolean;
  conversationKey: string | null;
  messageProps: ComponentProps<typeof SubagentThreadMessages>;
  retainedHistorySlotKey: string | null;
  historyStatus: ReactNode;
  navigationStatus: ReactNode;
  messages: UIMessage[];
  navigation?: PromptHistoryNavigation;
  navigationFrame?: HTMLElement | null;
  onJumpToPrompt: (id: string) => void;
  showLatestButton: boolean;
  scrollButtonBottom: number;
  onScrollLatest: () => void;
  onComposerInput: () => void;
}

export function ThreadViewportSurface({ nodes, setMessageRegion, setHistorySlot, hasMessages, hasThreadLayout,
  hasComposer, hasVerticalOverflow, scrollViewportStyle, composer, emptyState, initialLoading, conversationKey,
  messageProps, retainedHistorySlotKey, historyStatus, navigationStatus, messages, navigation, navigationFrame,
  onJumpToPrompt, showLatestButton, scrollButtonBottom, onScrollLatest, onComposerInput }: ViewportSurfaceProps) {
  const { viewportFrameRef, contentRef, messageContentRef, emptyStateRef, composerDockRef, bottomRef, scrollRef } = nodes;
  const { t } = useTranslation();
  return (
    <div className="thread-viewport relative flex min-h-0 flex-1 overflow-hidden">
      <div
        ref={viewportFrameRef}
        className={cn(
          "thread-viewport-frame absolute inset-0",
          hasMessages
            ? "overflow-hidden"
            : cn(
              "thread-viewport-scrollbar scroll-auto",
              "[overflow-anchor:none] [scrollbar-width:none]",
              "[&::-webkit-scrollbar]:hidden",
              hasVerticalOverflow ? "overflow-y-auto" : "overflow-hidden",
            ),
        )}
        style={scrollViewportStyle}
      >
        <div
          ref={contentRef}
          data-testid={!hasThreadLayout ? "thread-welcome-layout" : undefined}
          data-layout={hasComposer ? (hasThreadLayout ? "thread" : "hero") : "external"}
          className={cn(
            "thread-layout mx-auto grid min-h-full w-full",
            hasThreadLayout
              ? "h-full"
              : "max-w-[72rem] px-3 pb-[calc(0.75rem+env(safe-area-inset-bottom))] pt-6 @min-[640px]/cirno-tab:px-4 @min-[640px]/cirno-tab:py-12",
          )}
        >
          {hasMessages ? (
            <div
              ref={setMessageRegion}
              data-testid="thread-message-region"
              className={cn(
                "thread-message-viewport thread-viewport-scrollbar row-start-1 flex min-h-0 min-w-0 flex-col",
                "scroll-auto justify-start overflow-x-hidden overscroll-y-none pb-0 scroll-pt-12",
                "[overflow-anchor:none] [scrollbar-width:none]",
                "[&::-webkit-scrollbar]:hidden",
                hasVerticalOverflow ? "overflow-y-auto" : "overflow-hidden",
              )}
            >
              <div ref={messageContentRef} className="w-full">
                <DiagramScope identity={conversationKey}>
                  <SubagentThreadMessages {...messageProps} beforeUnit={retainedHistorySlotKey ? {
                    key: retainedHistorySlotKey, content: (
                      <div ref={setHistorySlot} className="thread-history-slot relative" style={{ height: HISTORY_HOLD_PX }}>
                        {historyStatus}
                      </div>
                    )
                  } : undefined} />
                </DiagramScope>
              </div>
              <div aria-hidden className="thread-message-end-gap shrink-0" />
              <div ref={bottomRef} aria-hidden className="h-px shrink-0" />
            </div>
          ) : (
            <div
              ref={emptyStateRef}
              data-testid="thread-empty-region"
              className={cn(
                "row-start-1 min-h-0 min-w-0 w-full",
                initialLoading
                  ? "overflow-hidden"
                  : cn("flex items-center justify-center", hasComposer && "@min-[640px]/cirno-tab:items-end @min-[640px]/cirno-tab:pb-8"),
              )}
            >
              {emptyState}
            </div>
          )}

          {hasComposer ? (
            <div
              ref={composerDockRef}
              data-testid="thread-composer-dock"
              data-theme-surface
              onInputCapture={(event) => {
                if (event.target instanceof HTMLTextAreaElement) {
                  onComposerInput();
                }
              }}
              className={cn(
                "row-start-2 z-10 w-full",
                hasThreadLayout ? "thread-composer-dock relative" : "relative self-center",
              )}
            >
              <div
                className={cn(
                  hasThreadLayout
                    ? "px-3 pb-[calc(0.5rem+env(safe-area-inset-bottom))] @min-[640px]/cirno-tab:px-4 @min-[640px]/cirno-tab:pb-[calc(0.75rem+env(safe-area-inset-bottom))]"
                    : "",
                )}
              >
                <div
                  data-testid="thread-composer-motion"
                  className="mx-auto w-full max-w-[58rem]"
                >
                  {composer}
                </div>
              </div>
            </div>
          ) : null}

          {hasComposer ? (
            <div
              aria-hidden
              className="thread-layout-spacer row-start-3 min-h-0 overflow-hidden"
            />
          ) : null}
        </div>
        {!retainedHistorySlotKey ? historyStatus : null}
        {navigationStatus}
        {!hasMessages ? <div ref={bottomRef} aria-hidden className="h-px" /> : null}
      </div>

      {hasMessages ? (
        <PromptRail
          messages={messages}
          prompts={navigation?.prompts}
          directory={navigation?.directory}
          scrollRef={scrollRef}
          navigationFrame={navigationFrame}
          onJumpToPrompt={onJumpToPrompt}
        />
      ) : null}

      {showLatestButton && (
        <div
          className="absolute left-1/2 z-20 -translate-x-1/2"
          style={{ bottom: scrollButtonBottom }}
        >
          <Button
            variant="outline"
            size="icon"
            onClick={onScrollLatest}
            className={cn(
              "h-8 w-8 rounded-full",
              "bg-background/90 backdrop-blur",
              "animate-in fade-in-0 zoom-in-95",
            )}
            aria-label={t("thread.scrollToBottom")}
          >
            <ArrowDown className="h-4 w-4" />
          </Button>
        </div>
      )}
    </div>
  );
}
