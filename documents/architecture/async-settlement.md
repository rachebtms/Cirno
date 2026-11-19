# Cancellation and durable settlement

Cancellation ends a caller's wait; it cannot undo a physical write already
accepted by a thread or a remote service. Code must identify the owner of that
operation and keep its receipt, draft acknowledgement and cleanup attached to it.

## Shared boundaries

| Boundary | Owner and contract |
| --- | --- |
| `shield_and_drain(awaitable)` | Finish the accepted operation before propagating caller cancellation, including repeated cancellation. Observe its outcome; if the caller cancelled, cancellation wins after settlement. |
| `SerializedThreadIO` | Serialize one storage owner's calls using the existing event-loop thread pool. A waiter may cancel before admission. After admission, retain the lock until physical I/O settles. |
| `SessionOperations` | Bound accepted session work, preserve key ordering and global barriers, and own its SQLite worker connections. Its `acknowledge` callback runs on the event loop after a successful worker result and before admission ownership is released. |

Use `SerializedThreadIO` for the notification inbox and delivery outbox. It is
not a replacement for the session operation queue: it has no capacity management,
key scheduling, connection ownership or shutdown policy.

## Commit and acknowledgement

Turn writes and recovery-checkpoint writes use `SessionOperations.execute` with
a synchronous `acknowledge` callback. Commit failure leaves the owner draft's
baseline unchanged. A committed result refreshes that baseline before the caller
can observe cancellation and retry. Checkpoint acknowledgement updates only its
committed fields, preserving unrelated local draft changes.

An acknowledgement failure still releases its queue key and reports the failure;
it does not undo or automatically repeat the already committed write. Later
operations on that key may proceed after settlement. Caller cancellation also
retains ownership if the physical worker subsequently fails: the worker outcome
is observed before cancellation propagates and a successor is admitted.

Acknowledgement callbacks must only update local receipts or drafts; they must
not submit another operation or start asynchronous work. External delivery and
multi-step cleanup keep their own domain settlement coroutine and use
`shield_and_drain` around that accepted unit.

## Distinct cancellation policies

Do not shield every read or replace every `asyncio.shield` mechanically. Ordinary
read results can be discarded when their caller leaves. Reads that share a
file handle, initialize a database or prune a queue may need settlement before
their owner closes or admits another operation. Session shutdown owns a separate
drain task: a caller may stop waiting without cancelling that internal drain.

Turn Stop materializes completed effects; service shutdown retains the recovery
checkpoint for restart. Those decisions remain in the turn lifecycle rather than
in generic I/O helpers. Delivery likewise keeps its pending/sent/unknown receipt
policy: a cancelled send may already have reached the channel and must not be
blindly replayed.

## Regression coverage

`test_thread_io.py` checks lock ownership through repeated cancellation, cancelled
waiters, results and errors. `test_turn_commit_cancellation.py` checks physical
commit failure, acknowledgement and idempotent retry for prepared input, finished
turns and recovery checkpoints. `test_delivery_io.py` checks event-loop
responsiveness and the durable receipt when cancellation interrupts record,
claim or finish. These tests use temporary storage and controlled workers, with
no provider or channel connection.
