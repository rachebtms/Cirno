import { completeProviderOAuth } from "@/lib/api";
import type { CirnoClient } from "@/lib/cirno-client";
import type { ProviderOAuthAuthorizationRequired } from "@/lib/contracts/models";
import type { SettingsPayload } from "@/lib/contracts/settings";
import { cancelAuthorization } from "./cancelAuthorization";

type Phase =
  | "waiting"
  | "completing"
  | "failed"
  | "cancelling"
  | "cancel_failed"
  | "complete"
  | "closed";
export interface AuthorizationSnapshot {
  phase: Phase;
  error: string | null;
}

/** One server login flow owns its polling, completion queue and cancellation. */
export class AuthorizationFlow {
  private snapshot: AuthorizationSnapshot = { phase: "waiting", error: null };
  private listeners = new Set<() => void>();
  private active = true;
  private timer: ReturnType<typeof setTimeout> | undefined;
  private tail: Promise<void> = Promise.resolve();
  private manual: Promise<void> | null = null;
  private cancellation: Promise<void> | null = null;

  constructor(
    private client: CirnoClient,
    readonly flow: ProviderOAuthAuthorizationRequired,
    private connected: (payload: SettingsPayload) => void,
    private closed: () => void,
  ) {}

  getSnapshot = () => this.snapshot;
  subscribe = (listener: () => void) => {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  };
  private publish(phase: Phase, error: string | null = null) {
    this.snapshot = { phase, error };
    this.listeners.forEach((listener) => listener());
  }
  private stopPolling() {
    clearTimeout(this.timer);
    this.timer = undefined;
  }
  start = () => {
    this.stopPolling();
    if (this.active)
      this.timer = setTimeout(() => {
        void this.poll();
      }, 1000);
  };
  poll = () => {
    if (!this.active) return Promise.resolve();
    this.stopPolling();
    this.publish(this.manual ? "completing" : "waiting");
    return this.request();
  };
  private request(response?: string) {
    const operation = this.tail.then(async () => {
      if (!this.active) return;
      let payload;
      try {
        payload = await completeProviderOAuth(
          this.client,
          this.flow.provider,
          this.flow.flow_id,
          response,
        );
      } catch (reason) {
        if (!this.active) return;
        this.stopPolling();
        this.publish("failed", reason instanceof Error ? reason.message : String(reason));
        return;
      }
      if (!this.active) return;
      if ("status" in payload && payload.status === "pending") {
        this.start();
        return;
      }
      this.active = false;
      this.stopPolling();
      this.publish("complete");
      this.connected(payload as SettingsPayload);
    });
    this.tail = operation;
    return operation;
  }
  submit = (response: string) => {
    if (!this.active || this.manual) return this.manual ?? Promise.resolve();
    this.stopPolling();
    this.publish("completing");
    const operation = this.request(response).finally(() => {
      if (this.manual === operation) this.manual = null;
      if (this.active && this.snapshot.phase === "completing") this.publish("waiting");
    });
    this.manual = operation;
    return operation;
  };
  private cancel() {
    if (this.cancellation) return this.cancellation;
    const operation = cancelAuthorization(this.client, this.flow).finally(() => {
      if (this.cancellation === operation) this.cancellation = null;
    });
    this.cancellation = operation;
    return operation;
  }
  close = async () => {
    if (["complete", "closed", "cancelling"].includes(this.snapshot.phase)) return;
    this.active = false;
    this.stopPolling();
    this.publish("cancelling");
    try {
      await this.cancel();
    } catch (reason) {
      this.publish("cancel_failed", reason instanceof Error ? reason.message : String(reason));
      return;
    }
    this.publish("closed");
    this.closed();
  };
  /** The caller reports disposal failures after the editor has unmounted. */
  dispose = () => {
    this.active = false;
    this.stopPolling();
    return this.snapshot.phase === "complete" || this.snapshot.phase === "closed"
      ? Promise.resolve()
      : this.cancel();
  };
}
