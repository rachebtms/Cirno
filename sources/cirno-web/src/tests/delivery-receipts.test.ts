import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { DeliveryReceipts } from "../../packages/client-events/delivery";

beforeEach(() => vi.useFakeTimers());
afterEach(() => { vi.clearAllTimers(); vi.useRealTimers(); });

it.each(["accepted", "rejected", "disconnected"])("settles every duplicate waiter when %s", async ending => {
  const receipts = new DeliveryReceipts();
  const send = vi.fn();
  const outcomes: string[] = [];
  const observe = (promise: Promise<void>) => promise.then(
    () => { outcomes.push("accepted"); }, () => { outcomes.push("rejected"); },
  );
  observe(receipts.wait("same-input", send));
  observe(receipts.wait("same-input", send));
  if (ending === "disconnected") receipts.close();
  else receipts.event({ event: ending === "accepted" ? "message_accepted" : "error", turn_id: "same-input" });
  await Promise.resolve();
  expect(outcomes).toEqual(ending === "accepted" ? ["accepted", "accepted"] : ["rejected", "rejected"]);
  expect(send).toHaveBeenCalledOnce();
});

it("keeps the original acceptance deadline when a pending input is submitted again", async () => {
  const receipts = new DeliveryReceipts();
  const send = vi.fn();
  const outcomes: unknown[] = [];
  const observe = (promise: Promise<void>) => promise.catch(error => { outcomes.push(error); });
  observe(receipts.wait("same-input", send));
  await vi.advanceTimersByTimeAsync(29_999);
  observe(receipts.wait("same-input", send));
  await vi.advanceTimersByTimeAsync(1);
  expect(outcomes).toHaveLength(2);
  expect(send).toHaveBeenCalledOnce();
  receipts.close();
});
