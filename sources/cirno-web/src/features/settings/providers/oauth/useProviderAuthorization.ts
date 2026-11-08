import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { loginProviderOAuth, logoutProviderOAuth } from "@/lib/api";
import type { CirnoClient } from "@/lib/cirno-client";
import type {
  ProviderOAuthAuthorizationRequired,
  ProviderOAuthLoginResult,
} from "@/lib/contracts/models";
import type { ApplySettingsPayload } from "../../contracts";
import type { ProviderOperation } from "../model/operations";
import { useLifetime } from "@/ui/resources/useLifetime";
import { useMutation } from "@/ui/resources/useMutation";
import { AuthorizationFlow, type AuthorizationSnapshot } from "./AuthorizationFlow";
import { releaseAuthorization, reportAuthorizationReleaseError } from "./releaseAuthorization";

const idle: AuthorizationSnapshot = { phase: "closed", error: null };
const idleSnapshot = () => idle;
const idleSubscribe = () => () => {};
const authorizationRequired = (
  value: ProviderOAuthLoginResult,
): value is ProviderOAuthAuthorizationRequired =>
  "status" in value && value.status === "authorization_required";

export function useProviderAuthorization({
  client,
  busy,
  remoteBrowserAccess,
  applyPayload,
  setError,
}: {
  client: CirnoClient;
  busy: boolean;
  remoteBrowserAccess: boolean;
  applyPayload: ApplySettingsPayload;
  setError: (value: string | null) => void;
}) {
  const isCurrent = useLifetime(client),
    mutation = useMutation(client);
  const [owned, setOwned] = useState<{ client: CirnoClient; resource: AuthorizationFlow } | null>(
    null,
  );
  const [operation, setOperation] = useState<{
    client: CirnoClient;
    value: ProviderOperation | null;
  }>({ client, value: null });
  const [answer, setAnswer] = useState<{ session: AuthorizationFlow; value: string } | null>(null);
  const resource = owned?.client === client ? owned.resource : null;
  const current = useRef(resource);
  current.current = resource;
  const snapshot = useSyncExternalStore(
    resource?.subscribe ?? idleSubscribe,
    resource?.getSnapshot ?? idleSnapshot,
  );
  useEffect(() => {
    resource?.start();
    return () => {
      if (resource)
        void resource
          .dispose()
          .catch((reason) => reportAuthorizationReleaseError(client, resource.flow, reason));
    };
  }, [client, resource]);
  useEffect(() => {
    if (mutation.error) setError(mutation.error);
  }, [mutation.error, setError]);

  const run = (provider: string, action: "login" | "logout") => {
    if (busy || !isCurrent()) return;
    let popup: Window | null = null;
    return mutation.run(
      async () => {
        if (action === "login" && provider === "xai_grok" && !remoteBrowserAccess) {
          try {
            popup = window.open("about:blank", "_blank");
            if (popup) popup.opener = null;
          } catch {
            /* The dialog retains the authorization link when popups are blocked. */
          }
        }
        setOperation({ client, value: { provider, action } });
        try {
          const previous = current.current;
          if (previous) {
            await previous.close();
            if (
              previous.getSnapshot().phase !== "closed" &&
              previous.getSnapshot().phase !== "complete"
            )
              return null;
          }
          if (!isCurrent()) return null;
          const result =
            action === "login"
              ? await loginProviderOAuth(
                  client,
                  provider,
                  provider === "openai_codex" && remoteBrowserAccess,
                )
              : await logoutProviderOAuth(client, provider);
          if (!isCurrent()) {
            popup?.close();
            if (authorizationRequired(result)) await releaseAuthorization(client, result);
            return null;
          }
          return result;
        } catch (reason) {
          popup?.close();
          throw reason;
        } finally {
          if (isCurrent()) setOperation({ client, value: null });
        }
      },
      (result) => {
        if (!result) return;
        setError(null);
        if (!authorizationRequired(result)) {
          popup?.close();
          applyPayload(result, { preserveAgentForm: true, preserveCapabilityForms: true });
          return;
        }
        const session = new AuthorizationFlow(
          client,
          result,
          (payload) => {
            if (!isCurrent() || current.current !== session) return;
            current.current = null;
            setOwned(null);
            setAnswer(null);
            applyPayload(payload, { preserveAgentForm: true, preserveCapabilityForms: true });
            setError(null);
          },
          () => {
            if (isCurrent() && current.current === session) {
              current.current = null;
              setOwned(null);
              setAnswer(null);
            }
          },
        );
        current.current = session;
        setOwned({ client, resource: session });
        setAnswer(null);
        if (popup && !popup.closed) popup.location.href = result.authorization_url;
      },
    );
  };
  const response = answer?.session === resource ? answer.value : "";
  return {
    flow: resource?.flow ?? null,
    response,
    setResponse: (value: string) => {
      if (resource && current.current === resource && isCurrent())
        setAnswer({ session: resource, value });
    },
    operation: operation.client === client ? operation.value : null,
    error: snapshot.error,
    completing: snapshot.phase === "completing",
    cancelling: snapshot.phase === "cancelling",
    canComplete: !["cancelling", "cancel_failed"].includes(snapshot.phase),
    login: (provider: string) => run(provider, "login"),
    logout: (provider: string) => run(provider, "logout"),
    complete: () => resource?.submit(response.trim()),
    close: () => resource?.close(),
    retry: () => (snapshot.phase === "cancel_failed" ? resource?.close() : resource?.poll()),
  };
}
export type ProviderAuthorization = ReturnType<typeof useProviderAuthorization>;
