import { isModelInput } from "@/lib/thread-inputs";
import { Fragment, memo, useCallback, useEffect, useId, useMemo, useRef, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { MessageActions, MessageBubble } from "@/features/messages";
import { AgentActivityCluster } from "@/components/thread/AgentActivityCluster";
import { AssistantSelectionAction } from "@/components/thread/AssistantSelectionAction";
import { usePreferences } from "@/hooks/usePreferences";
import { projectActivityTimeline, type TurnUnit } from "@/lib/activity-timeline";
import { groupRouterActivity } from "@/lib/router-activity-timeline";
import { cn } from "@/lib/utils";
import type { CliAppInfo } from "@/lib/contracts/apps";
import type { McpPresetInfo } from "@/lib/contracts/mcp";
import type { RetryStatus, UIMessage } from "@/lib/contracts/messages";
import type { SlashCommand } from "@/lib/contracts/commands";

export interface MessageEditorSlot {
  messageId: string;
  content: ReactNode;
}

interface ThreadMessagesProps {
  messageEditor?: MessageEditorSlot;
  defaultActivityCollapsed?: boolean;
  assistantBubbles?: boolean;
  activityGrouping?: "turn" | "conversation";
  messages: UIMessage[];
  beforeMessages?: ReactNode;
  beforeUnit?: { key: string; content: ReactNode };
  topInset?: number;
  afterUserMessage?: (message: UIMessage) => ReactNode;
  afterMessages?: ReactNode;
  temporary?: boolean;
  /** When true, agent turn still in flight — keeps activity timeline expanded. */
  isStreaming?: boolean;
  activeTurnId?: string | null;
  /** Optimistic or canonical active-turn start, in unix seconds. */
  runStartedAt?: number | null;
  retryStatus?: RetryStatus | null;
  hiddenUserMessageCount?: number;
  cliApps?: CliAppInfo[];
  mcpPresets?: McpPresetInfo[];
  slashCommands?: SlashCommand[];
  forkBoundaryMessageCount?: number | null;
  traceDetailScope?: string | null;
  onLoadTraceDetails?: (refs: string[]) => void | Promise<void>;
  onOpenFilePreview?: (path: string) => void;
  onForkFromMessage?: (beforeUserIndex: number) => void;
  onEditMessage?: (message: UIMessage) => void;
  onQuoteSelection?: (text: string) => void;
  onActivityToggle?: () => void;
}

export type DisplayUnit = TurnUnit;

export function buildDisplayUnits(messages: UIMessage[], preserveReplyBoundaries = false): DisplayUnit[] {
  return projectActivityTimeline(messages.filter(message => !message.questionCancellation), { preserveReplyBoundaries }).filter(unit => unit.type !== "message" || !unit.message.userQuestion);
}

export function assistantForkFlags(units: DisplayUnit[]): boolean[] {
  const flags = new Array<boolean>(units.length).fill(true);
  let hasLaterUnitBeforeUser = false;
  for (let i = units.length - 1; i >= 0; i -= 1) {
    const unit = units[i];
    if (unit.type === "message" && unit.message.role === "user") {
      hasLaterUnitBeforeUser = false;
      continue;
    }
    if (
      unit.type === "message"
      && unit.message.role === "assistant"
      && unit.message.kind === "compaction"
    ) {
      // Compaction notices are session lifecycle markers, not assistant answers.
      // They must neither expose nor displace the answer-level fork action.
      flags[i] = false;
      continue;
    }
    if (unit.type === "message" && unit.message.role === "assistant") {
      flags[i] = !hasLaterUnitBeforeUser;
    }
    hasLaterUnitBeforeUser = true;
  }
  return flags;
}

export function ThreadMessages({
  messageEditor,
  defaultActivityCollapsed = false,
  assistantBubbles = false,
  activityGrouping = "turn",
  messages,
  beforeMessages,
  beforeUnit,
  topInset = 0,
  afterUserMessage,
  afterMessages,
  temporary = false,
  isStreaming = false,
  activeTurnId = null,
  runStartedAt = null,
  retryStatus = null,
  hiddenUserMessageCount = 0,
  cliApps = [],
  mcpPresets = [],
  slashCommands = [],
  forkBoundaryMessageCount = null,
  traceDetailScope = null,
  onLoadTraceDetails,
  onOpenFilePreview,
  onForkFromMessage,
  onEditMessage,
  onQuoteSelection,
  onActivityToggle,
}: ThreadMessagesProps) {
  const { t } = useTranslation();
  const { activityMode } = usePreferences();
  const messageListRef = useRef<HTMLDivElement>(null);
  const units = useMemo(
    () => {
      const projected = buildDisplayUnits(defaultActivityCollapsed ? messages : messages.map(message =>
        message.activityKind === "model" && message.content.trim()
          ? { ...message, activityKind: undefined, turnPhase: "answer" as const } : message), assistantBubbles);
      return activityGrouping === "conversation" ? groupRouterActivity(projected) : projected;
    },
    [activityGrouping, assistantBubbles, defaultActivityCollapsed, messages],
  );
  const forkBoundaryAfterUnitIndex = useMemo(
    () => unitIndexAfterMessageCount(units, forkBoundaryMessageCount),
    [forkBoundaryMessageCount, units],
  );
  const forkFlags = useMemo(() => assistantForkFlags(units), [units]);
  const liveActivityClusterIndices = useMemo(
    () => isStreaming
      ? currentActivityClusterIndices(units, activeTurnId)
      : new Set<number>(),
    [activeTurnId, isStreaming, units],
  );
  const pendingTurn = useMemo(
    () => pendingTurnProjection(messages, activeTurnId),
    [activeTurnId, messages],
  );
  const pendingActivity = (
    isStreaming
    && liveActivityClusterIndices.size === 0
    && pendingTurn !== null
    && (retryStatus !== null || !pendingTurn.hasVisibleOutput)
  ) ? pendingTurn : null;
  const currentTurnStartIndex = isStreaming
    ? activeTurnStartIndex(units, activeTurnId)
    : units.length;
  const unitKeys = useMemo(() => unitKeysForDisplay(units), [units]);
  const messageBlocks = useMemo(
    () => completedMessageBlocks(
      units,
      unitKeys,
      isStreaming,
      activeTurnId,
      currentTurnStartIndex,
      defaultActivityCollapsed,
    ),
    [activeTurnId, currentTurnStartIndex, defaultActivityCollapsed, isStreaming, unitKeys, units],
  );
  const [activityOverrides, setActivityOverrides] = useState<Map<string, boolean>>(() => new Map());
  useEffect(() => {
    setActivityOverrides(new Map());
  }, [activityMode]);
  const setActivityExpanded = useCallback((key: string, expanded: boolean) => {
    onActivityToggle?.();
    setActivityOverrides((current) => {
      if (current.get(key) === expanded) return current;
      const next = new Map(current);
      next.set(key, expanded);
      return next;
    });
  }, [onActivityToggle]);
  let nextUserIndex = hiddenUserMessageCount;
  const preludeIndex = Math.max(0, beforeUnit ? unitKeys.indexOf(beforeUnit.key) : 0);
  const inset = topInset > 0 ? <div aria-hidden style={{ height: topInset }} /> : null;
  const preludeInset = preludeIndex === 0 ? inset : null;
  const renderPrelude = (prefix: ReactNode, marginTop?: string) => prefix || preludeInset || beforeMessages
    ? <div key="thread-prelude" className={cn("flow-root", marginTop)}>{prefix}{preludeInset}{beforeMessages}</div> : null;

  return (
    <div ref={messageListRef} className="flex w-full flex-col">
      <AssistantSelectionAction
        containerRef={messageListRef}
        onQuoteSelection={onQuoteSelection}
      />
      {[
        preludeIndex > 0 ? <Fragment key="top-inset">{inset}</Fragment> : null,
        units.length === 0 ? renderPrelude(null) : null,
        ...units.flatMap((unit, index) => {
        const next = units[index + 1];
        const hasBodyBelow =
          unit.type === "activity"
          && next?.type === "message"
          && next.message.role === "assistant";
        const contextBlockKey = messageBlocks.blockKeys[index]
          ?? (unit.type === "message" && unit.message.role === "user"
            ? `message-block-${unitKeys[index]}`
            : undefined);
        const showBlockContext = messageBlocks.blockIndices.has(index);
        const blockActivity = messageBlocks.activityByBlock.get(index);
        const suppressActivity = messageBlocks.suppressedActivityIndices.has(index);
        const previousVisibleIndex = previousVisibleUnitIndex(
          index,
          messageBlocks.suppressedActivityIndices,
        );
        const marginTop = suppressActivity || previousVisibleIndex < 0
          ? ""
          : marginAfterPrevUnit(units[previousVisibleIndex]);
        const blockActivityExpanded = showBlockContext
          && contextBlockKey !== undefined
          && (activityOverrides.get(contextBlockKey) ?? (!defaultActivityCollapsed && activityMode === "expanded"));
        const deferOffscreenRender =
          index < units.length - 1
          && (
            unit.type === "activity"
              ? !liveActivityClusterIndices.has(index)
              : unit.message.role === "assistant" && !unit.message.isStreaming
          );
        const userPromptId =
          unit.type === "message" && unit.message.role === "user"
            ? unit.message.id
            : undefined;
        const forkIndex =
          unit.type === "message" && unit.message.role === "assistant" && forkFlags[index]
            ? nextUserIndex
            : undefined;
        const unitTurnStreaming = unit.type === "activity"
          ? liveActivityClusterIndices.has(index)
          : isStreaming && (
              unit.message.turnId && activeTurnId !== null
                ? unit.message.turnId === activeTurnId
                : index > currentTurnStartIndex
            );
        if (
          unit.type === "message"
          && isModelInput(unit.message)
        ) nextUserIndex += 1;
        if (unit.type === "activity") nextUserIndex += unit.messages.filter(isModelInput).length;

        const prefix = beforeUnit?.key === unitKeys[index] ? beforeUnit.content : null;
        const prelude = index === preludeIndex ? renderPrelude(prefix, marginTop) : null;
        return [
          prelude,
          <Fragment key={`unit:${unitKeys[index]}`}>
          <ThreadDisplayUnit
            key={unitKeys[index]}
            unitKey={unitKeys[index]}
            unit={unit}
            marginTop={prelude ? "" : marginTop}
            userPromptId={userPromptId}
            hasBodyBelow={hasBodyBelow}
            suppressActivity={suppressActivity}
            showBlockContext={showBlockContext}
            blockActivity={blockActivity}
            assistantBubbles={assistantBubbles}
            defaultActivityCollapsed={defaultActivityCollapsed}
            blockActivityExpanded={blockActivityExpanded}
            contextBlockKey={contextBlockKey}
            deferOffscreenRender={deferOffscreenRender}
            isTurnStreaming={unitTurnStreaming}
            retryStatus={
              unit.type === "activity" && liveActivityClusterIndices.has(index)
                ? retryStatus
                : null
            }
            forkIndex={forkIndex}
            showForkBoundary={index === forkBoundaryAfterUnitIndex}
            forkBoundaryLabel={t("thread.forkedFromHistory")}
            temporary={temporary}
            cliApps={cliApps}
            mcpPresets={mcpPresets}
            slashCommands={slashCommands}
            traceDetailScope={traceDetailScope}
            onLoadTraceDetails={onLoadTraceDetails}
            onOpenFilePreview={onOpenFilePreview}
            onForkFromMessage={onForkFromMessage}
            editor={unit.type === "message" && unit.message.id === messageEditor?.messageId ? messageEditor.content : undefined}
            onEditMessage={isStreaming ? undefined : onEditMessage}
            onActivityExpandedChange={setActivityExpanded}
            afterInputMessage={afterUserMessage}
          />
          {unit.type === "message" && unit.message.role === "user" ? (
            afterUserMessage?.(unit.message)
          ) : null}
          </Fragment>,
        ];
      })]}
      {afterMessages}
      {pendingActivity ? (
        <div className={cn("thread-message-row", units.length > 0 && "mt-5")}>
          <AgentActivityCluster
            defaultCollapsed={defaultActivityCollapsed}
            messages={[]}
            isTurnStreaming
            hasBodyBelow={false}
            retryStatus={retryStatus}
            startedAtMs={
              // Match the activity timeline's prompt-based clock across the first output.
              pendingActivity.startedAtMs ?? (runStartedAt != null ? runStartedAt * 1000 : undefined)
            }
          />
        </div>
      ) : null}
    </div>
  );
}

interface PendingTurnProjection {
  startedAtMs?: number;
  hasVisibleOutput: boolean;
}

function pendingTurnProjection(
  messages: UIMessage[],
  activeTurnId: string | null,
): PendingTurnProjection | null {
  let promptIndex = -1;
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = messages[index];
    if (
      message.role === "user"
      && message.deliveryStatus !== "failed"
      && (activeTurnId === null || message.turnId === activeTurnId)
    ) {
      promptIndex = index;
      break;
    }
  }
  if (promptIndex < 0) return null;

  const prompt = messages[promptIndex];
  const hasVisibleOutput = messages.slice(promptIndex + 1).some((message) => {
    if (message.role === "user") return false;
    if (activeTurnId && message.turnId && message.turnId !== activeTurnId) return false;
    return (
      message.content.trim().length > 0
      || !!message.reasoning?.trim()
      || !!message.reasoningStreaming
      || message.kind === "trace"
      || !!message.media?.length
    );
  });

  return {
    ...(typeof prompt.createdAt === "number" && Number.isFinite(prompt.createdAt)
      ? { startedAtMs: prompt.createdAt }
      : {}),
    hasVisibleOutput,
  };
}

interface ThreadDisplayUnitProps {
  afterInputMessage?: (message: UIMessage) => ReactNode;
  editor?: ReactNode;
  unitKey: string;
  unit: DisplayUnit;
  marginTop: string;
  userPromptId?: string;
  hasBodyBelow: boolean;
  suppressActivity: boolean;
  showBlockContext: boolean;
  blockActivity?: Extract<DisplayUnit, { type: "activity" }>;
  defaultActivityCollapsed: boolean;
  assistantBubbles: boolean;
  blockActivityExpanded: boolean;
  contextBlockKey?: string;
  deferOffscreenRender: boolean;
  isTurnStreaming: boolean;
  retryStatus: RetryStatus | null;
  forkIndex?: number;
  showForkBoundary: boolean;
  forkBoundaryLabel: string;
  temporary: boolean;
  cliApps: CliAppInfo[];
  mcpPresets: McpPresetInfo[];
  slashCommands: SlashCommand[];
  traceDetailScope: string | null;
  onLoadTraceDetails?: (refs: string[]) => void | Promise<void>;
  onOpenFilePreview?: (path: string) => void;
  onForkFromMessage?: (beforeUserIndex: number) => void;
  onEditMessage?: (message: UIMessage) => void;
  onActivityExpandedChange: (key: string, expanded: boolean) => void;
}

const ThreadDisplayUnit = memo(function ThreadDisplayUnit({
  editor,
  unitKey,
  unit,
  marginTop,
  userPromptId,
  hasBodyBelow,
  suppressActivity,
  showBlockContext,
  blockActivity,
  defaultActivityCollapsed,
  assistantBubbles,
  blockActivityExpanded,
  contextBlockKey,
  deferOffscreenRender,
  isTurnStreaming,
  retryStatus,
  forkIndex,
  showForkBoundary,
  forkBoundaryLabel,
  temporary,
  cliApps,
  mcpPresets,
  slashCommands,
  traceDetailScope,
  onLoadTraceDetails,
  onOpenFilePreview,
  onForkFromMessage,
  onEditMessage,
  onActivityExpandedChange,
  afterInputMessage,
}: ThreadDisplayUnitProps) {
  const elementRef = useRef<HTMLDivElement>(null);
  const activityDetailsId = useId();
  const heightRef = useRef(0);
  const [nearViewport, setNearViewport] = useState(true);
  const [interacted, setInteracted] = useState(false);
  const retainContent = !deferOffscreenRender || interacted || nearViewport;
  useEffect(() => {
    const element = elementRef.current;
    if (!element || !deferOffscreenRender || interacted || typeof IntersectionObserver === "undefined") return;
    const observer = new IntersectionObserver((entries) => {
      const entry = entries[entries.length - 1];
      if (!entry) return;
      if (!entry.isIntersecting) {
        const height = element.getBoundingClientRect().height;
        if (height <= 0) return;
        heightRef.current = height;
      }
      setNearViewport(entry.isIntersecting);
    }, { rootMargin: "1000px 0px" });
    observer.observe(element);
    return () => observer.disconnect();
  }, [deferOffscreenRender, interacted]);
  const onForkFromHere = useCallback(() => {
    if (forkIndex !== undefined) onForkFromMessage?.(forkIndex);
  }, [forkIndex, onForkFromMessage]);
  const onBlockActivityExpandedChange = useCallback((expanded: boolean) => {
    if (contextBlockKey !== undefined) {
      onActivityExpandedChange(contextBlockKey, expanded);
      window.setTimeout(() => {
        const focusTarget = elementRef.current?.querySelector<HTMLElement>(
          "[data-contextual-activity-disclosure]",
        );
        focusTarget?.focus({ preventScroll: true });
      }, 0);
    }
  }, [contextBlockKey, onActivityExpandedChange]);
  const actions = !editor && unit.type === "message" && unit.message.kind !== "compaction" ? <MessageActions
    message={unit.message} isTurnStreaming={isTurnStreaming}
    onForkFromHere={forkIndex !== undefined && onForkFromMessage ? onForkFromHere : undefined}
    onEdit={onEditMessage && !temporary && unit.message.role === "user" && !unit.message.inputOrigin && !unit.message.sessionMessage && unit.message.turnId && !isTurnStreaming
      ? () => onEditMessage(unit.message) : undefined}
  /> : null;
  return (
    <>
      <div
        ref={elementRef}
        className={cn(
          "thread-message-row",
          marginTop,
          "relative",
        )}
        style={retainContent ? undefined : { height: heightRef.current }}
        onPointerDownCapture={() => {
          setInteracted(true);
        }}
        data-thread-display-unit={unitKey}
        data-user-prompt-id={userPromptId}
        data-message-context-block={contextBlockKey}
        onFocusCapture={() => setInteracted(true)}
      >
        {unit.type === "activity" ? unit.messages.filter(message => message.role === "user").map(message => (
          <span key={message.id} data-user-prompt-id={message.id} aria-hidden className="pointer-events-none absolute top-0 h-0 w-0" />
        )) : null}
        {retainContent ? unit.type === "activity" ? (
          suppressActivity ? null : (
            <AgentActivityCluster
              defaultCollapsed={defaultActivityCollapsed}
              messages={unit.messages}
              isTurnStreaming={isTurnStreaming}
              retryStatus={retryStatus}
              hasBodyBelow={hasBodyBelow}
              turnLatencyMs={unit.turnLatencyMs}
              startedAtMs={unit.startedAtMs}
              elapsedBeforeActiveMs={unit.elapsedBeforeActiveMs}
              afterInputMessage={afterInputMessage}
              cliApps={cliApps}
              mcpPresets={mcpPresets}
              traceDetailScope={traceDetailScope}
              onLoadTraceDetails={onLoadTraceDetails}
              onOpenFilePreview={onOpenFilePreview}
            />
          )
        ) : (
          <div className={unit.message.role === "assistant" ? "relative" : undefined}>
            {showBlockContext && blockActivity ? (
              <div className={blockActivityExpanded ? "mb-2" : undefined}>
                <AgentActivityCluster
                  defaultCollapsed={defaultActivityCollapsed}
                  messages={blockActivity.messages}
                  isTurnStreaming={false}
                  retryStatus={null}
                  hasBodyBelow={false}
                  expanded={blockActivityExpanded}
                  onExpandedChange={onBlockActivityExpandedChange}
                  detailsId={activityDetailsId}
                  turnLatencyMs={blockActivity.turnLatencyMs}
                  startedAtMs={blockActivity.startedAtMs}
                  cliApps={cliApps}
                  mcpPresets={mcpPresets}
                  traceDetailScope={traceDetailScope}
                  onLoadTraceDetails={onLoadTraceDetails}
                  onOpenFilePreview={onOpenFilePreview}
                />
              </div>
            ) : null}
            <MessageBubble
              editor={editor}
              message={unit.message}
              assistantBubble={assistantBubbles}
              temporary={temporary}
              cliApps={cliApps}
              mcpPresets={mcpPresets}
              slashCommands={slashCommands}
              onOpenFilePreview={onOpenFilePreview}
            />
            {actions}
          </div>
        ) : null}
      </div>
      {showForkBoundary ? <ForkBoundaryDivider label={forkBoundaryLabel} /> : null}
    </>
  );
}, threadDisplayUnitPropsEqual);

function threadDisplayUnitPropsEqual(
  previous: ThreadDisplayUnitProps,
  next: ThreadDisplayUnitProps,
): boolean {
  return (
    previous.editor === next.editor
    && previous.afterInputMessage === next.afterInputMessage
    && displayUnitsEqual(previous.unit, next.unit)
    && previous.marginTop === next.marginTop
    && previous.userPromptId === next.userPromptId
    && previous.hasBodyBelow === next.hasBodyBelow
    && previous.suppressActivity === next.suppressActivity
    && previous.showBlockContext === next.showBlockContext
    && previous.blockActivity === next.blockActivity
    && previous.assistantBubbles === next.assistantBubbles
    && previous.defaultActivityCollapsed === next.defaultActivityCollapsed
    && previous.blockActivityExpanded === next.blockActivityExpanded
    && previous.contextBlockKey === next.contextBlockKey
    && previous.deferOffscreenRender === next.deferOffscreenRender
    && previous.isTurnStreaming === next.isTurnStreaming
    && previous.retryStatus === next.retryStatus
    && previous.forkIndex === next.forkIndex
    && previous.showForkBoundary === next.showForkBoundary
    && previous.forkBoundaryLabel === next.forkBoundaryLabel
    && previous.temporary === next.temporary
    && previous.cliApps === next.cliApps
    && previous.mcpPresets === next.mcpPresets
    && previous.slashCommands === next.slashCommands
    && previous.traceDetailScope === next.traceDetailScope
    && previous.onLoadTraceDetails === next.onLoadTraceDetails
    && previous.onOpenFilePreview === next.onOpenFilePreview
    && previous.onForkFromMessage === next.onForkFromMessage
    && previous.onEditMessage === next.onEditMessage
    && previous.onActivityExpandedChange === next.onActivityExpandedChange
  );
}

function activeTurnStartIndex(units: DisplayUnit[], activeTurnId: string | null): number {
  if (activeTurnId) {
    const index = units.findIndex((unit) => (
      unit.type === "message"
      && unit.message.role === "user"
      && unit.message.deliveryStatus !== "failed"
      && unit.message.turnId === activeTurnId
    ));
    if (index >= 0) return index;
  }
  for (let i = units.length - 1; i >= 0; i -= 1) {
    const unit = units[i];
    if (
      unit.type === "message"
      && unit.message.role === "user"
      && unit.message.deliveryStatus !== "failed"
    ) return i;
  }
  return -1;
}

function displayUnitsEqual(previous: DisplayUnit, next: DisplayUnit): boolean {
  if (previous.type !== next.type) return false;
  if (previous.type === "message" && next.type === "message") {
    return (
      previous.sourceMessageCount === next.sourceMessageCount
      && shallowMessageEqual(previous.message, next.message)
    );
  }
  if (previous.type !== "activity" || next.type !== "activity") return false;
  return (
    previous.sourceMessageCount === next.sourceMessageCount
    && previous.turnLatencyMs === next.turnLatencyMs
    && previous.startedAtMs === next.startedAtMs
    && previous.elapsedBeforeActiveMs === next.elapsedBeforeActiveMs
    && previous.messages.length === next.messages.length
    && previous.messages.every((message, index) =>
      shallowMessageEqual(message, next.messages[index]))
  );
}

function shallowMessageEqual(previous: UIMessage, next: UIMessage): boolean {
  if (previous === next) return true;
  const previousKeys = Object.keys(previous) as Array<keyof UIMessage>;
  const nextKeys = Object.keys(next) as Array<keyof UIMessage>;
  return previousKeys.length === nextKeys.length
    && previousKeys.every((key) => previous[key] === next[key]);
}

function unitIndexAfterMessageCount(
  units: DisplayUnit[],
  messageCount: number | null | undefined,
): number | null {
  if (messageCount == null || messageCount <= 0) return null;
  let seen = 0;
  for (let i = 0; i < units.length; i += 1) {
    const unit = units[i];
    seen += unit.sourceMessageCount;
    if (seen >= messageCount) return i;
  }
  return null;
}

function ForkBoundaryDivider({ label }: { label: string }) {
  return (
    <div className="thread-message-row my-5 flex items-center gap-3 text-[11px] text-muted-foreground/80">
      <span aria-hidden className="h-px flex-1 bg-border/70" />
      <span className="shrink-0">{label}</span>
      <span aria-hidden className="h-px flex-1 bg-border/70" />
    </div>
  );
}

function currentActivityClusterIndices(
  units: DisplayUnit[],
  activeTurnId: string | null,
): Set<number> {
  const indices = new Set<number>();
  if (activeTurnId) {
    for (let i = units.length - 1; i >= 0; i -= 1) {
      const unit = units[i];
      if (
        unit.type === "activity"
        && unit.messages.some((message) => message.turnId === activeTurnId)
      ) {
        indices.add(i);
        return indices;
      }
    }
  }

  let markedCurrentActivity = false;
  for (let i = units.length - 1; i >= 0; i -= 1) {
    const unit = units[i];
    if (unit.type === "activity") {
      if (!markedCurrentActivity) {
        indices.add(i);
        markedCurrentActivity = true;
      }
      continue;
    }
    if (unit.message.role === "assistant" && unit.message.isStreaming) continue;
    if (unit.message.role === "user") break;
  }
  return indices;
}

export function unitKeysForDisplay(units: DisplayUnit[]): string[] {
  const occurrences = new Map<string, number>();
  return units.map((unit, index) => {
    const base = unitKeyBase(unit, index);
    if (!base.startsWith("turn-")) return base;
    const next = (occurrences.get(base) ?? 0) + 1;
    occurrences.set(base, next);
    return base.endsWith("-user") && next === 1 ? base : `${base}-${next}`;
  });
}

function unitKeyBase(unit: DisplayUnit, index: number): string {
  if (unit.type === "activity") {
    const anchor = unit.messages[0];
    const turnKey = stableTurnMessageKey(anchor, "activity");
    if (turnKey) return turnKey;
    const anchorId = anchor?.id;
    return anchorId != null ? `activity-${anchorId}` : `activity-idx-${index}`;
  }
  const turnKey = stableTurnMessageKey(unit.message);
  if (turnKey) return turnKey;
  return unit.message.id;
}

function stableTurnMessageKey(message: UIMessage | undefined, fallbackPhase?: string): string | null {
  if (!message?.turnId) return null;
  const phase = message.turnPhase ?? fallbackPhase ?? message.kind ?? message.role;
  if (message.role === "user") return `turn-${message.turnId}-user`;
  if (message.kind === "trace") {
    return `turn-${message.turnId}-${phase}-${message.activitySegmentId ?? "activity"}`;
  }
  return `turn-${message.turnId}-${phase}`;
}

function marginAfterPrevUnit(
  prev: DisplayUnit,
): string {
  if (prev.type === "activity") {
    return "mt-4";
  }
  const p = prev.message;
  const denseP =
    p.kind === "trace"
    || (
      p.role === "assistant"
      && p.content.trim().length === 0
      && (!!p.reasoning || !!p.reasoningStreaming)
    );
  if (denseP) {
    return "mt-2";
  }
  if (p.role === "assistant" && !p.isStreaming && p.content.trim().length > 0) {
    return "mt-5";
  }
  return "mt-5";
}

interface CompletedMessageBlocks {
  blockKeys: Array<string | undefined>;
  blockIndices: Set<number>;
  suppressedActivityIndices: Set<number>;
  activityByBlock: Map<number, Extract<DisplayUnit, { type: "activity" }>>;
}

function completedMessageBlocks(
  units: DisplayUnit[],
  unitKeys: string[],
  isStreaming: boolean,
  activeTurnId: string | null,
  currentTurnStartIndex: number,
  standaloneActivity = false,
): CompletedMessageBlocks {
  const result: CompletedMessageBlocks = {
    blockKeys: new Array<string | undefined>(units.length),
    blockIndices: new Set<number>(),
    suppressedActivityIndices: new Set<number>(),
    activityByBlock: new Map(),
  };
  if (standaloneActivity) return result;
  let groupStart = 0;
  let groupTurnId: string | undefined;

  const flushGroup = (end: number) => {
    if (groupStart >= end) return;
    const indices = Array.from({ length: end - groupStart }, (_, offset) => groupStart + offset);
    const groupIsStreaming = isStreaming && indices.some((index) => {
      const unit = units[index];
      const turnId = displayUnitTurnId(unit);
      if (activeTurnId && turnId) return turnId === activeTurnId;
      return index > currentTurnStartIndex;
    });
    if (groupIsStreaming) return;

    const blockIndices = indices.filter((index) => {
      const unit = units[index];
      return unit.type === "message"
        && unit.message.role === "assistant"
        && unit.message.kind !== "compaction";
    });
    for (const index of blockIndices) {
      result.blockIndices.add(index);
      result.blockKeys[index] = `message-block-${unitKeys[index]}`;
    }

    const activityByBlock = new Map<number, Array<Extract<DisplayUnit, { type: "activity" }>>>();
    for (const index of indices) {
      const unit = units[index];
      if (unit.type !== "activity") continue;
      const blockIndex = blockIndices.find((candidate) => candidate > index) ?? blockIndices.at(-1);
      if (blockIndex === undefined) continue;
      result.suppressedActivityIndices.add(index);
      const activityUnits = activityByBlock.get(blockIndex) ?? [];
      activityUnits.push(unit);
      activityByBlock.set(blockIndex, activityUnits);
    }
    for (const [blockIndex, activityUnits] of activityByBlock) {
      result.activityByBlock.set(blockIndex, mergeActivityUnits(activityUnits));
    }
  };

  for (let index = 0; index < units.length; index += 1) {
    const unit = units[index];
    if (unit.type === "message" && unit.message.role === "user") {
      flushGroup(index);
      groupStart = index + 1;
      groupTurnId = unit.message.turnId;
      continue;
    }
    const turnId = displayUnitTurnId(unit);
    if (turnId && groupTurnId && turnId !== groupTurnId) {
      flushGroup(index);
      groupStart = index;
      groupTurnId = turnId;
    } else if (turnId && !groupTurnId) {
      groupTurnId = turnId;
    }
  }
  flushGroup(units.length);
  return result;
}

function mergeActivityUnits(
  units: Array<Extract<DisplayUnit, { type: "activity" }>>,
): Extract<DisplayUnit, { type: "activity" }> {
  return {
    type: "activity",
    messages: units.flatMap((unit) => unit.messages),
    sourceMessageCount: units.reduce((count, unit) => count + unit.sourceMessageCount, 0),
    turnLatencyMs: [...units].reverse().find((unit) => unit.turnLatencyMs !== undefined)
      ?.turnLatencyMs,
    startedAtMs: units.find((unit) => unit.startedAtMs !== undefined)?.startedAtMs,
  };
}

function displayUnitTurnId(unit: DisplayUnit): string | undefined {
  return unit.type === "activity"
    ? unit.messages.find((message) => message.turnId)?.turnId
    : unit.message.turnId;
}

function previousVisibleUnitIndex(
  index: number,
  suppressedActivityIndices: ReadonlySet<number>,
): number {
  for (let previous = index - 1; previous >= 0; previous -= 1) {
    if (!suppressedActivityIndices.has(previous)) return previous;
  }
  return -1;
}
