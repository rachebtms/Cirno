import { createContext, useContext, useEffect, useId, useMemo, useRef, useState, type ReactNode } from "react";
import { Check, ChevronDown, ChevronUp, CircleHelp, Loader2, Send, Square } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { parseQuotedUserMessage } from "@/lib/user-message-quote";
import type { UIMessage, UserQuestion } from "@/lib/types";

type AnswerState = { answer: string; status: UIMessage["deliveryStatus"] };
type ReplyContext = { questions: UserQuestion[]; answers: Map<string, AnswerState>; send?: (question: UserQuestion, answer: string) => boolean | Promise<boolean> };
const QuestionReplies = createContext<ReplyContext>({ questions: [], answers: new Map() });

export function QuestionReplyProvider({ messages, send, children }: {
  messages: UIMessage[]; send: ReplyContext["send"]; children: ReactNode;
}) {
  const [accepted, setAccepted] = useState(new Map<string, string>());
  const questions = useMemo(() => [...new Map(messages.filter(message => message.userQuestion).map(message => [message.userQuestion!.id, message.userQuestion!])).values()], [messages]);
  const answers = useMemo(() => {
    const result = new Map<string, AnswerState>();
    for (const message of messages) {
      if (message.role !== "user") continue;
      const quote = parseQuotedUserMessage(message.content);
      if (quote.questionId) result.set(quote.questionId, { answer: quote.content, status: message.deliveryStatus });
    }
    for (const [id, answer] of accepted) {
      if (result.get(id)?.status !== "failed") result.set(id, { answer, status: undefined });
    }
    return result;
  }, [messages, accepted]);
  const submit: ReplyContext["send"] = useMemo(() => send ? async (question, answer) => {
    const delivered = await send(question, answer);
    if (delivered) setAccepted(previous => new Map(previous).set(question.id, answer));
    return delivered;
  } : undefined, [send]);
  const value = useMemo(() => ({ questions, answers, send: submit }), [questions, answers, submit]);
  return <QuestionReplies.Provider value={value}>{children}</QuestionReplies.Provider>;
}

export function UserQuestionCard({ question, header }: { question: UserQuestion; header?: ReactNode }) {
  const { t } = useTranslation();
  const { answers, send } = useContext(QuestionReplies);
  const otherInputId = useId();
  const response = answers.get(question.id);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const sending = useRef(false);
  const answered = response && response.status !== "sending" && response.status !== "failed";
  const pending = busy || response?.status === "sending";
  const submit = async (answer: string) => {
    if (!send || sending.current || pending || answered || !answer.trim()) return;
    sending.current = true; setBusy(true); setError(""); setDraft(answer);
    try {
      if (!await send(question, answer.trim())) setError(t("userQuestion.sendFailed"));
    } catch (reason) { setError(reason instanceof Error ? reason.message : t("userQuestion.sendFailed")); }
    finally { sending.current = false; setBusy(false); }
  };
  return <section aria-label={t("userQuestion.title")} className="min-w-0 overflow-hidden rounded-prominent border border-input bg-settings-surface shadow-sm">
    {header ?? <div className="flex items-center gap-2 px-4 pt-4 text-xs text-muted-foreground"><CircleHelp className="size-4 shrink-0" aria-hidden />{t("userQuestion.title")}</div>}
    <div className="max-h-[min(50dvh,28rem)] overflow-y-auto overscroll-contain px-4 pb-4 pt-3 sm:px-5 sm:pb-5">
    <p className="whitespace-pre-wrap break-words text-reading font-medium">{question.question}</p>
    {question.assumption && <p className="mt-2 whitespace-pre-wrap break-words text-sm text-muted-foreground">{t("userQuestion.assumption", { assumption: question.assumption })}</p>}
    {answered ? <div className="mt-3 flex min-w-0 items-start gap-2 text-sm"><Check className="mt-0.5 size-4 shrink-0 text-emerald-500" aria-hidden /><div className="min-w-0"><p className="text-xs text-muted-foreground">{t("userQuestion.answered")}</p><p className="whitespace-pre-wrap break-words">{response.answer}</p></div></div>
      : <form className="mt-3 space-y-2" onSubmit={event => { event.preventDefault(); void submit(draft); }}>
        {question.options.map(option => <Button key={option} type="button" variant="outline" disabled={!send || pending} className="h-auto min-h-11 w-full justify-start px-3 py-3 text-left" onClick={() => void submit(option)}><span className="min-w-0 flex-1 whitespace-pre-wrap font-normal leading-6 [overflow-wrap:anywhere]">{option}</span></Button>)}
        <div className="min-w-0 rounded-control border border-input p-3">
          <label htmlFor={otherInputId} className="mb-2 block text-sm font-medium">{t("userQuestion.other")}</label>
          <Textarea id={otherInputId} placeholder={t("userQuestion.placeholder")} value={draft} onChange={event => setDraft(event.target.value)} maxLength={8000} disabled={!send || pending} rows={2} className="min-h-16 resize-y" />
          <div className="mt-2 flex justify-end"><Button type="submit" size="sm" className="shrink-0 gap-2" disabled={!send || pending || !draft.trim()}>{pending ? <Loader2 className="size-4 animate-spin" aria-hidden /> : <Send className="size-4" aria-hidden />}{t("userQuestion.send")}</Button></div>
        </div>
        <p className="pt-1 text-xs leading-5 text-muted-foreground">{t("userQuestion.nonBlocking")}</p>
      </form>}
    {(error || response?.status === "failed") && <p role="alert" className="mt-2 break-words text-sm text-destructive">{error || t("userQuestion.sendFailed")}</p>}
    </div>
  </section>;
}


/** The queue shares the composer slot; conversation history keeps only the evidence. */
export function UserQuestionQueue({ children, isStreaming = false, onStop }: {
  children: ReactNode; isStreaming?: boolean; onStop?: () => void;
}) {
  const { t } = useTranslation();
  const { questions, answers } = useContext(QuestionReplies);
  const pending = questions.filter(question => {
    const answer = answers.get(question.id);
    return !answer || answer.status === "sending" || answer.status === "failed";
  });
  const active = pending[0];
  const [minimized, setMinimized] = useState(false);
  const composerRef = useRef<HTMLDivElement>(null);
  const hadQuestions = useRef(false);
  useEffect(() => {
    if (active && !hadQuestions.current) {
      const focused = document.activeElement;
      const typing = focused instanceof HTMLTextAreaElement && composerRef.current?.contains(focused) && focused.value.trim();
      setMinimized(Boolean(typing));
    }
    hadQuestions.current = Boolean(active);
  }, [active]);
  const count = t("userQuestion.remaining", { count: pending.length });
  const header = <div className="flex min-w-0 items-center gap-2 border-b border-border/60 px-3 py-2 sm:px-4">
    <CircleHelp className="size-4 shrink-0 text-muted-foreground" aria-hidden />
    <span className="min-w-0 flex-1 text-sm font-medium" role="status">{count}</span>
    {isStreaming && onStop && <Button type="button" variant="ghost" size="icon" className="size-8 shrink-0" aria-label={t("thread.composer.stop")} onClick={onStop}><Square className="size-3.5" aria-hidden /></Button>}
    <Button type="button" variant="ghost" size="sm" className="shrink-0 gap-1.5 text-xs text-muted-foreground" onClick={() => setMinimized(true)}>{t("userQuestion.writeMessage")}<ChevronDown className="size-3.5" aria-hidden /></Button>
  </div>;
  return <div data-testid="user-question-queue" className="min-w-0">
    {active && <>
      {minimized && <Button type="button" variant="ghost" className="mb-2 h-auto min-h-9 w-full justify-between gap-2 px-3 py-2 text-left text-sm" aria-label={t("userQuestion.showQuestions", { count: pending.length })} onClick={() => setMinimized(false)}><span className="flex min-w-0 items-center gap-2"><CircleHelp className="size-4 shrink-0" aria-hidden /><span className="whitespace-normal">{count}</span></span><ChevronUp className="size-4 shrink-0" aria-hidden /></Button>}
      <div hidden={minimized}><UserQuestionCard key={active.id} question={active} header={header} /></div>
    </>}
    <div ref={composerRef} hidden={Boolean(active) && !minimized}>{children}</div>
  </div>;
}
