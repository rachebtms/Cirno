import { parseQuotedUserMessage } from "@/lib/user-message-quote";
import type { UserQuestion } from "@/lib/types";

export function parseUserQuestion(blob: unknown): UserQuestion | undefined {
  if (!blob || typeof blob !== "object" || !("kind" in blob) || blob.kind !== "user_question" || !("data" in blob)) return;
  const data = blob.data;
  if (!data || typeof data !== "object") return;
  const q = data as Record<string, unknown>;
  if (typeof q.id !== "string" || !/^[a-f0-9]{32}$/.test(q.id)
    || typeof q.question !== "string" || !q.question.trim() || q.question.length > 2000
    || !Array.isArray(q.options) || q.options.length > 6
    || q.options.some(option => typeof option !== "string" || !option.trim() || option.length > 200)
    || typeof q.assumption !== "string" || q.assumption.length > 1000) return;
  return { id: q.id, question: q.question, options: q.options as string[], assumption: q.assumption };
}

/** Persist correlation in the existing quoted-message format, hidden from the user. */
export function formatQuestionAnswer(question: UserQuestion, answer: string): string {
  const quote = `<!-- cirno-question:${question.id} -->\n${question.question}`;
  return `> [!QUOTE]\n${quote.split("\n").map(line => line ? `> ${line}` : ">").join("\n")}\n\n${answer.trim()}`;
}

export function questionReplyPreview(text: string): string {
  const parsed = parseQuotedUserMessage(text);
  return parsed.questionId ? parsed.content || parsed.quotedContext || "" : text;
}
