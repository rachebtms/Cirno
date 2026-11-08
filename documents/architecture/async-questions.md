# Asynchronous questions

The logical operation `user.ask` posts questions without waiting for an answer. Native function calling uses `user__ask`; PTC uses `await tools.user.ask(...)`. A call accepts either `questions=[{question, options?, assumption?}, ...]` with up to eight questions, or the single-question fields `question`, `options` and `assumption`. Each question allows up to six suggested answers.

The entire batch is validated before delivery. A partial delivery error identifies questions already sent so the caller can avoid duplicating them. Posting a question neither creates a waiting Goal nor blocks independent work. Missing required information blocks only the dependent step; an unanswered question is not authorization.

## Browser queue

Questions appear at the composer, rather than as cards between chat messages. The first unanswered question is shown with the remaining count; later calls append to the queue. Options occupy separate rows and wrap when necessary. The final row accepts a free-text answer. Selecting an option sends it; the queue advances only after the send succeeds.

The user can temporarily switch to the ordinary composer and return without losing an answer draft. Answering the last question restores the message draft. Stop cancels execution without deleting pending questions. On narrow screens the question area scrolls independently. Interface labels follow the selected UI language; the model supplies question and option text in the user's language.

## Replies and persistence

Replies carry the original question and a hidden correlation marker through the existing quotation and steering protocol:

- During execution, an answer steers the same conversation without sending Stop or starting a parallel turn.
- After execution, it becomes follow-up input to that conversation.
- A failed send retains the answer for retry and does not mark it answered.

Question payloads use `_agent_ui` in the stored assistant activity stream. Browser history projection hides their inline cards and builds the composer queue from questions and accepted user replies. Refreshes and other connected clients can recover the accepted answer state. Accepted answers mark the corresponding Inbox item answered and read. Unsent drafts do not survive a page reload. The feature uses conversation storage rather than a separate question database or waiting worker.

Router and Worker conversations can both ask questions. A question does not count as delivery of a final reply. Telegram displays question text and accepts ordinary quoted chat replies. Use the authenticated Web UI to answer a linked Inbox question and update its queue state. The sequential question composer and queue controls are Web-only.

## Withdrawing obsolete questions

Router and Workers can call `user__cancel_ask(question_id=..., reason=...)` (PTC: `await tools.user.cancel_ask(...)`) with an ID returned by `user.ask`. Withdrawal uses the same durable channel as the original question and returns `cancellation_queued`; it does not wait for a browser. It removes that question from the composer queue, marks its pending Inbox item withdrawn and read, and retains its history and optional reason. Delivery replay cannot reopen an answered or withdrawn Inbox item. Answer and withdrawal transitions preserve whichever terminal state was recorded first.

Withdrawal is scoped to the current conversation and history generation. An unknown ID has no effect; answered records remain answered. It is appropriate when a question has become irrelevant, not as a substitute for required permission. Cancellation events are replayed with conversation history so refreshing or reconnecting does not bring the question back.
