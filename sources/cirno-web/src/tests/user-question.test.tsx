import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { QuestionReplyProvider, UserQuestionCard, UserQuestionQueue } from "@/components/thread/UserQuestionCard";
import { ThreadMessages } from "@/components/thread/ThreadMessages";
import { formatQuestionAnswer, parseUserQuestion, questionReplyPreview } from "@/lib/user-question";
import { parseQuotedUserMessage } from "@/lib/user-message-quote";
import { projectThreadEvents } from "@/lib/thread-event-projection";
import { normalizeActivityTimeline } from "@/lib/activity-timeline";
import type { UIMessage, UserQuestion } from "@/lib/types";

const question: UserQuestion = { id: "a".repeat(32), question: "Which export format?", options: ["CSV", "JSON"], assumption: "I will inspect the files first." };
const second: UserQuestion = { ...question, id: "b".repeat(32), question: "Which language?", options: ["English", "中文"] };
const questionMessage = (q: UserQuestion): UIMessage => ({ id: q.id, role: "assistant", content: q.question, userQuestion: q, createdAt: 1 });

it("round-trips quoted answers without exposing correlation IDs or executing slash commands", () => {
  const text = formatQuestionAnswer(question, "/stop is a literal answer");
  expect(text.startsWith("> [!QUOTE]")).toBe(true);
  expect(questionReplyPreview(text)).toBe("/stop is a literal answer");
  expect(parseQuotedUserMessage(text)).toEqual({ questionId: question.id, quotedContext: question.question, content: "/stop is a literal answer" });
  expect(parseUserQuestion({ kind: "user_question", data: question })).toEqual(question);
  expect(parseUserQuestion({ kind: "user_question", data: { ...question, options: [false] } })).toBeUndefined();
});

it("keeps a question distinct from earlier and later assistant output on replay", () => {
  const messages = projectThreadEvents([
    { event: "delta", chat_id: "a", turn_id: "t", stream_id: "before", turn_seq: 1, text: "Before" },
    { event: "message", chat_id: "a", turn_id: "t", turn_seq: 2, text: question.question, agent_ui: { kind: "user_question", data: question } },
    { event: "delta", chat_id: "a", turn_id: "t", stream_id: "after", turn_seq: 3, text: "Work continues" },
    { event: "stream_end", chat_id: "a", turn_id: "t", stream_id: "after", turn_seq: 4, text: "Work continues" },
  ]);
  expect(normalizeActivityTimeline(messages).filter(unit => unit.type === "message").map(unit => unit.message.content)).toEqual(["Before", question.question, "Work continues"]);
  render(<QuestionReplyProvider messages={messages} send={vi.fn()}>
    <div data-testid="history"><ThreadMessages defaultActivityCollapsed messages={messages} /></div>
    <UserQuestionQueue><textarea aria-label="Message" /></UserQuestionQueue>
  </QuestionReplyProvider>);
  expect(within(screen.getByTestId("history")).queryByRole("region", { name: "A question for you" })).toBeNull();
  expect(within(screen.getByTestId("user-question-queue")).getByRole("button", { name: "CSV" })).toBeEnabled();
});

it("restores accepted answers from history and only answers the matching question", () => {
  const messages: UIMessage[] = [{ id: "reply", role: "user", content: formatQuestionAnswer(question, "JSON"), createdAt: 1 }];
  render(<QuestionReplyProvider messages={messages} send={vi.fn()}>
    <UserQuestionCard question={question} /><UserQuestionCard question={{ ...question, id: "b".repeat(32) }} />
  </QuestionReplyProvider>);
  expect(screen.getByText("Your answer", { selector: "p" })).toBeVisible();
  expect(screen.getAllByRole("button", { name: "JSON" })).toHaveLength(1);
  expect(screen.getAllByRole("textbox")).toHaveLength(1);
});

it("sends an option immediately and retains a free-text answer after failure", async () => {
  const send = vi.fn().mockResolvedValueOnce(false).mockResolvedValueOnce(true);
  render(<QuestionReplyProvider messages={[]} send={send}><UserQuestionCard question={question} /></QuestionReplyProvider>);
  fireEvent.click(screen.getByRole("button", { name: "CSV" }));
  await waitFor(() => expect(send).toHaveBeenCalledWith(question, "CSV"));
  expect(await screen.findByRole("alert")).toHaveTextContent("Could not send");
  expect(screen.getByRole("textbox")).toHaveValue("CSV");
  fireEvent.change(screen.getByRole("textbox"), { target: { value: "A custom format" } });
  fireEvent.click(screen.getByRole("button", { name: "Reply" }));
  await waitFor(() => expect(send).toHaveBeenLastCalledWith(question, "A custom format"));
});

it("does not treat a pending or rejected optimistic message as an accepted answer", () => {
  const response: UIMessage = { id: "reply", role: "user", content: formatQuestionAnswer(question, "JSON"), createdAt: 1, deliveryStatus: "sending" };
  const view = render(<QuestionReplyProvider messages={[response]} send={vi.fn()}><UserQuestionCard question={question} /></QuestionReplyProvider>);
  expect(screen.getByRole("button", { name: "CSV" })).toBeDisabled();
  view.rerender(<QuestionReplyProvider messages={[{ ...response, deliveryStatus: "failed" }]} send={vi.fn()}><UserQuestionCard question={question} /></QuestionReplyProvider>);
  expect(screen.getByRole("button", { name: "CSV" })).toBeEnabled();
  expect(screen.getByRole("alert")).toBeVisible();
});

it("queues batch and later questions in order, advancing only after successful delivery", async () => {
  const send = vi.fn().mockResolvedValueOnce(false).mockResolvedValue(true);
  const third = { ...question, id: "c".repeat(32), question: "Which destination?" };
  const ui = (messages: UIMessage[]) => <QuestionReplyProvider messages={messages} send={send}>
    <UserQuestionQueue><textarea aria-label="Message" defaultValue="Unsent message" /></UserQuestionQueue>
  </QuestionReplyProvider>;
  const view = render(ui([questionMessage(question), questionMessage(second)]));
  expect(screen.getByRole("status")).toHaveTextContent("2 questions remaining");
  expect(screen.queryByText(second.question)).toBeNull();
  expect(screen.getByLabelText("Message")).not.toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "CSV" }));
  expect(await screen.findByRole("alert")).toBeVisible();
  expect(screen.getByText(question.question)).toBeVisible();
  view.rerender(ui([questionMessage(question), questionMessage(second), questionMessage(third)]));
  expect(screen.getByRole("status")).toHaveTextContent("3 questions remaining");
  fireEvent.click(screen.getByRole("button", { name: "JSON" }));
  await waitFor(() => expect(screen.getByText(second.question)).toBeVisible());
  expect(screen.getByRole("status")).toHaveTextContent("2 questions remaining");
  fireEvent.click(screen.getByRole("button", { name: "English" }));
  await waitFor(() => expect(screen.getByText(third.question)).toBeVisible());
  expect(screen.getByRole("status")).toHaveTextContent("1 question remaining");
  fireEvent.click(screen.getByRole("button", { name: "CSV" }));
  await waitFor(() => expect(screen.queryByRole("region", { name: "A question for you" })).toBeNull());
  expect(screen.getByLabelText("Message")).toBeVisible();
  expect(screen.getByLabelText("Message")).toHaveValue("Unsent message");
  expect(send.mock.calls.map(([q, answer]) => [q.id, answer])).toEqual([
    [question.id, "CSV"], [question.id, "JSON"], [second.id, "English"], [third.id, "CSV"],
  ]);
});

it("restores the queue from history, ignoring duplicates and already answered questions", () => {
  render(<QuestionReplyProvider messages={[
    questionMessage(question), questionMessage(second), questionMessage(second),
    { id: "answer", role: "user", createdAt: 2, content: formatQuestionAnswer(question, "JSON") },
  ]} send={vi.fn()}><UserQuestionQueue><textarea aria-label="Message" /></UserQuestionQueue></QuestionReplyProvider>);
  expect(screen.getByText(second.question)).toBeVisible();
  expect(screen.queryByText(question.question)).toBeNull();
  expect(screen.getByRole("status")).toHaveTextContent("1 question remaining");
});

it("allows ordinary messages and stopping work without losing an unfinished question answer", () => {
  const stop = vi.fn();
  render(<QuestionReplyProvider messages={[questionMessage(question)]} send={vi.fn()}>
    <UserQuestionQueue isStreaming onStop={stop}><textarea aria-label="Message" defaultValue="My message" /></UserQuestionQueue>
  </QuestionReplyProvider>);
  fireEvent.change(screen.getByRole("textbox", { name: "Other" }), { target: { value: "A draft answer" } });
  fireEvent.click(screen.getByRole("button", { name: "Stop response" }));
  expect(stop).toHaveBeenCalledOnce();
  fireEvent.click(screen.getByRole("button", { name: "Write message" }));
  expect(screen.getByLabelText("Message")).toBeVisible();
  expect(screen.getByLabelText("Message")).toHaveValue("My message");
  expect(screen.queryByRole("region", { name: "A question for you" })).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Answer queued questions (1)" }));
  expect(screen.getByRole("textbox", { name: "Other" })).toHaveValue("A draft answer");
});
