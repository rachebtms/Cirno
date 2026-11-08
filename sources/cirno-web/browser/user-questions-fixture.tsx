import { useState } from "react";

import { QuestionReplyProvider, UserQuestionQueue } from "@/components/thread/UserQuestionCard";
import { ThreadComposer } from "@/components/thread/ThreadComposer";
import { formatQuestionAnswer } from "@/lib/user-question";
import type { UIMessage, UserQuestion } from "@/lib/contracts/messages";

const questions: UserQuestion[] = [
  { id: "a".repeat(32), question: "Which format should I use for the verified measurements and their original units?",
    options: ["CSV with original units and a separate description of every measurement column", "JSON"], assumption: "I will keep checking the evidence while you decide." },
  { id: "b".repeat(32), question: "Which language should the report use?", options: ["English", "中文"], assumption: "" },
];
const initial: UIMessage[] = questions.map(question => ({ id: question.id, role: "assistant", content: question.question, userQuestion: question, createdAt: 1 }));

export function UserQuestionsFixture() {
  const [messages, setMessages] = useState(initial);
  return <main className="flex min-h-screen flex-col bg-background p-4 text-foreground">
    <div><button onClick={() => setMessages(initial)}>Rewind answer</button></div>
    <div className="flex-1" />
    <section className="mx-auto w-full max-w-3xl">
      <QuestionReplyProvider messages={messages} send={async (question, answer) => {
        setMessages(previous => [...previous, { id: "reply-" + question.id, role: "user", content: formatQuestionAnswer(question, answer), createdAt: 2 }]);
        return true;
      }}>
        <UserQuestionQueue><ThreadComposer onSend={() => true} workspaceControlsHidden /></UserQuestionQueue>
      </QuestionReplyProvider>
    </section>
  </main>;
}
