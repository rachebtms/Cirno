import { InterfaceProvider } from "@/providers/InterfaceProvider";
import { OperationNotices } from "@/ui/feedback/OperationNotices";
import {
  BrowserNotifications,
  useBrowserNotificationLifecycle,
} from "@/components/BrowserNotifications";
import { AccountEntry } from "@/features/entry/AccountEntry";
import { AccessEntry } from "@/features/entry/AccessEntry";
import { StartupShell } from "@/components/StartupShell";
import {
  clearOwnerPreferences,
  receivePreferences,
} from "@/features/preferences/store";
import { useAppViewport } from "@/hooks/useAppViewport";
import { InboxProvider } from "@/features/inbox/model/store";
import { usePreferences } from "@/hooks/usePreferences";
import { useReadingTypography } from "@/hooks/useReadingTypography";
import { applyServerLanguage } from "@/i18n";
import { accountRequest } from "@/lib/account";
import {
  BootstrapAuthRequiredError,
  clearSavedSecret,
  consumeUrlBootstrapSecret,
  deriveWsUrl,
  fetchBootstrap,
  loadSavedSecret,
  saveSecret,
} from "@/lib/bootstrap";
import { CirnoClient } from "@/lib/cirno-client";
import { clearBrowserDrafts } from "./clearBrowserDrafts";
import { activateReloadCache, clearReloadCache } from "@/lib/reload-cache";
import { webuiThreadCache } from "@/lib/webui-thread-cache";
import { ClientProvider } from "@/providers/ClientProvider";
import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  bootstrapTokenExpiresAt,
  tokenRefreshDelayMs,
} from "./token-expiry";
import {
  BootState,
  bootstrapCapabilities,
  loadThreadShell,
  SetupFlow,
  readShellRoute,
} from "./navigation";
import { Shell } from "./Shell";
import { isBootstrapAuthRequired } from "./workspace-layout";
export function App({ migrationErrors }: { migrationErrors?: readonly string[] } = {}) {
  return <InterfaceProvider><ApplicationBootstrap /><OperationNotices initialErrors={migrationErrors} /></InterfaceProvider>;
}

function ApplicationBootstrap() {
  useAppViewport();
  useBrowserNotificationLifecycle();
  useReadingTypography();
  const preferences = usePreferences();
  useEffect(() => {
    void applyServerLanguage(preferences.language);
  }, [preferences.language]);
  const { t } = useTranslation();
  const [state, setState] = useState<BootState>({ status: "loading" });
  const bootstrapSecretRef = useRef("");

  const refreshReadyClient = useCallback(
    async (client: CirnoClient) => {
      const boot = await fetchBootstrap("", bootstrapSecretRef.current);
      const url = deriveWsUrl(boot.ws_path, boot.token, boot.ws_url);
      const tokenExpiresAt = boot.expires_in
        ? bootstrapTokenExpiresAt(boot.expires_in)
        : null;
      client.updateUrl(url);
      client.updateMaxFrameBytes(boot.limits?.transport.max_frame_bytes);
      setState((current) =>
        current.status === "ready" && current.client === client
          ? {
            ...current,
            token: boot.api_token ?? "",
            tokenExpiresAt,
            modelName: boot.model_name ?? current.modelName,
            ingressLimits: boot.limits ?? current.ingressLimits,
            webuiCapabilities: bootstrapCapabilities(boot),
          }
          : current,
      );
      return { token: boot.api_token ?? "", url };
    },
    [],
  );

  const bootstrapWithSecret = useCallback(
    (secret: string) => {
      let cancelled = false;
      if (readShellRoute().view === "chat")
        void loadThreadShell().catch(() => { });
      (async () => {
        setState({ status: "loading" });
        try {
          const boot = await fetchBootstrap("", secret);
          if (cancelled) return;
          receivePreferences(boot.preferences);
          if (secret) saveSecret(secret);
          const url = deriveWsUrl(boot.ws_path, boot.token, boot.ws_url);
          activateReloadCache(url);
          const client = new CirnoClient({
            url,
            maxFrameBytes: boot.limits?.transport.max_frame_bytes,
            onReauth: async () => {
              try {
                const refreshed = await refreshReadyClient(
                  client,
                );
                return refreshed.url;
              } catch {
                return null;
              }
            },
          });
          bootstrapSecretRef.current = secret;
          client.connect();
          setState({
            status: "ready",
            client,
            token: boot.api_token ?? "",
            tokenExpiresAt: boot.expires_in
              ? bootstrapTokenExpiresAt(boot.expires_in)
              : null,
            modelName: boot.model_name ?? null,
            ingressLimits: boot.limits ?? null,
            webuiCapabilities: bootstrapCapabilities(boot),
            accountAuth: boot.browser_auth === true,
            onboardingRequired: boot.onboarding_required === true,
          });
        } catch (e) {
          if (cancelled) return;
          if (isBootstrapAuthRequired(e)) {
            clearReloadCache();
            clearBrowserDrafts();
            webuiThreadCache.clear();
            setState({
              status: "auth",
              failed: !!secret,
              accountMode:
                e instanceof BootstrapAuthRequiredError
                  ? e.accountMode
                  : undefined,
            });
          } else {
            setState({
              status: "error",
              message: e instanceof Error ? e.message : String(e),
            });
          }
        }
      })();
      return () => {
        cancelled = true;
      };
    },
    [refreshReadyClient],
  );

  useEffect(() => {
    if (state.status !== "ready" || state.tokenExpiresAt === null) return;
    const client = state.client;
    const timer = window.setTimeout(async () => {
      try {
        await refreshReadyClient(client);
      } catch (e) {
        if (isBootstrapAuthRequired(e)) {
          clearReloadCache();
          clearBrowserDrafts();
          webuiThreadCache.clear();
          client.close();
          setState({
            status: "auth",
            failed: !!bootstrapSecretRef.current,
            accountMode:
              e instanceof BootstrapAuthRequiredError
                ? e.accountMode
                : undefined,
          });
        }
      }
    }, tokenRefreshDelayMs(state.tokenExpiresAt));
    return () => window.clearTimeout(timer);
  }, [refreshReadyClient, state]);

  useEffect(() => {
    const saved = consumeUrlBootstrapSecret() || loadSavedSecret();
    return bootstrapWithSecret(saved);
  }, [bootstrapWithSecret]);

  if (state.status === "loading") {
    return <StartupShell />;
  }
  if (state.status === "auth") {
    if (state.accountMode)
      return (
        <AccountEntry
          key={state.accountMode}
          mode={state.accountMode}
          onSuccess={() => {
            clearSavedSecret();
            clearOwnerPreferences();
            bootstrapWithSecret("");
          }}
        />
      );
    return (
      <AccessEntry
        failed={!!state.failed}
        onSecret={(s) => bootstrapWithSecret(s)}
      />
    );
  }
  if (state.status === "error") {
    return (
      <div className="flex h-full w-full items-center justify-center px-4 text-center">
        <div className="flex max-w-md flex-col items-center gap-3">
          <p className="text-lg font-semibold">{t("app.error.title")}</p>
          <p className="text-sm text-muted-foreground">{state.message}</p>
          <p className="text-xs text-muted-foreground">
            {t("app.error.serverHint")}
          </p>
        </div>
      </div>
    );
  }

  const handleModelNameChange = (modelName: string | null) => {
    setState((current) =>
      current.status === "ready" ? { ...current, modelName } : current,
    );
  };

  const handleLogout = async () => {
    if (state.accountAuth) {
      try {
        await accountRequest("logout");
      } catch (error) {
        setState({
          status: "error",
          message: error instanceof Error ? error.message : String(error),
        });
        state.client.close();
        return;
      }
    }
    if (state.status === "ready") {
      state.client.close();
    }
    clearSavedSecret();
    clearOwnerPreferences();
    clearReloadCache();
    clearBrowserDrafts();
    webuiThreadCache.clear();
    setState({
      status: "auth",
      accountMode: state.accountAuth ? "login" : undefined,
    });
  };

  return (
    <ClientProvider
      client={state.client}
      token={state.token}
      modelName={state.modelName}
      ingressLimits={state.ingressLimits}
      webuiCapabilities={state.webuiCapabilities}
    >
      {state.onboardingRequired ? (
        <Suspense fallback={<StartupShell />}>
          <SetupFlow
            onModelNameChange={handleModelNameChange}
            onComplete={() =>
              setState((current) =>
                current.status === "ready"
                  ? { ...current, onboardingRequired: false }
                  : current,
              )
            }
          />
        </Suspense>
      ) : (
        <InboxProvider>
          <BrowserNotifications client={state.client} />
          <Shell
            onModelNameChange={handleModelNameChange}
            onLogout={handleLogout}
          />
        </InboxProvider>
      )}
    </ClientProvider>
  );
}
