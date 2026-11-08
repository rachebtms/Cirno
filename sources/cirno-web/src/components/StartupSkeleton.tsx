export type StartupSurface = "chat" | "settings" | "skills" | "apps" | "channels" | "automations" | "remote";

/** Also inlined in index.html: keep document startup independent of app modules. */
export function readStartupLayout() {
  let hash = window.location.hash.slice(1);
  try {
    if ((!hash || hash === "/" || hash === "/new")
      && Date.now() - Number(localStorage.getItem("cirno-webui.restartStartedAt") || 0) < 300_000) {
      hash = (localStorage.getItem("cirno-webui.restartRoute") || hash).replace(/^#/, "");
    }
  } catch {
    // Storage can be unavailable in private browsing; use the shell's defaults.
  }
  const [path, query = ""] = hash.split("?", 2);
  const section = new URLSearchParams(query).get("section") || "overview";
  const page = path === "/settings" ? section : path.slice(1);
  let surface: StartupSurface = "chat";
  if (page === "skills" || page === "apps" || page === "channels" || page === "automations" || page === "remote") surface = page;
  else if (path === "/settings") surface = "settings";
  const now = new Date();
  const firstDay = new Date(now.getFullYear(), now.getMonth(), 1);
  const days = new Date(now.getFullYear(), now.getMonth() + 1, 0).getDate();
  const calendarWeeks = Math.ceil(((firstDay.getDay() + 6) % 7 + days) / 7);
  return { surface, section, calendarWeeks, existingChat: /^\/(chat|temporary)\/.+/.test(path) };
}

interface StartupSkeletonProps {
  surface?: StartupSurface;
  section?: string;
  existingChat?: boolean;
  calendarWeeks?: number;
  embedded?: boolean;
  label?: string;
}

function Block({ className = "" }: { className?: string }) {
  return <div className={`startup-block ${className}`} />;
}

/** One markup/CSS contract for the HTML first paint and React's loading boundaries. */
export function StartupSkeleton({
  surface = "chat", section = "overview",
  existingChat = false, calendarWeeks = 5, embedded = false, label = "Loading Cirno…",
}: StartupSkeletonProps) {
  const Root = embedded ? "section" : "main";
  return (
    <Root className="startup-shell" aria-busy="true" data-startup-surface={surface}
      data-startup-section={section} data-existing-chat={existingChat}
      data-calendar-weeks={calendarWeeks} data-embedded={embedded}>
      <span className="startup-status" role="status" data-boot-copy>{label}</span>
      <div className="startup-navigation" aria-hidden="true">
        <div className="startup-nav-items">
          {Array.from({ length: 9 }, (_, index) => <div key={index} className="startup-nav-row"><Block className="startup-nav-icon" /></div>)}
        </div>
        <div className="startup-nav-utilities">
          {[0, 1].map(index => <div key={index} className="startup-nav-row"><Block className="startup-nav-icon" /></div>)}
        </div>
      </div>
      <div className="startup-content" aria-hidden="true">
        <div className="startup-workspace-tabs"><Block /></div>
        <div className="startup-chat">
          <div className="startup-chat-header">
            <div className="startup-header-leading"><div className="startup-header-menu"><Block /></div><Block className="startup-header-title" /></div>
            <div className="startup-header-actions"><div><Block /></div><div><Block /></div><div><Block /></div><div><Block /></div></div>
          </div>
          <div className="startup-chat-viewport">
            <div className="startup-chat-layout">
              <div className="startup-messages"><Block /><Block /><Block /></div>
              <div className="startup-welcome"><div className="startup-welcome-line"><Block /></div></div>
              <div className="startup-composer">
                <div className="startup-composer-surface">
                  <div className="startup-composer-input"><Block /></div>
                  <div className="startup-composer-footer">
                    <div className="startup-composer-primary"><Block className="startup-attach" /><Block className="startup-access" /></div>
                    <div className="startup-composer-actions"><Block className="startup-model" /><Block className="startup-send" /></div>
                  </div>
                </div>
                <div className="startup-workspace-row"><Block className="startup-workspace" /></div>
              </div>
              <div className="startup-chat-spacer" />
            </div>
          </div>
        </div>
        <div className="startup-scroll">
          <div className="startup-page">
            <div className="startup-page-header"><div className="startup-back"><Block /></div><div className="startup-title"><Block /></div></div>
            <div className="startup-tabs"><Block /></div>
            <div className="startup-panel">
              <div className="startup-toolbar"><Block className="startup-search" /><Block className="startup-filters" /></div>
              <div className="startup-catalog-frame">
              <div className="startup-catalog-heading"><Block /></div>
              <div className="startup-catalog">
                <div className="startup-catalog-group"><Block /></div>
                {Array.from({ length: 6 }, (_, index) => <div key={index} className="startup-catalog-row">
                  <Block className="startup-catalog-icon" /><div className="startup-catalog-copy"><Block /><Block /></div><Block className="startup-catalog-action" />
                </div>)}
              </div>
              </div>
            </div>
            <div className="startup-automation">
              <div className="startup-automation-composer"><Block /></div>
              <div className="startup-calendar"><div className="startup-calendar-toolbar"><Block /><Block /><Block className="startup-calendar-navigation" /></div>
                <div className="startup-calendar-days">{Array.from({ length: 42 }, (_, index) => <div key={index}><Block /></div>)}</div>
              </div>
            </div>
            <div className="startup-settings">
              {[0, 1].map((group) => <div key={group} className="startup-settings-group"><Block className="startup-settings-title" />
                {[0, 1, 2].map((row) => <div key={row} className="startup-settings-row"><Block /><Block /></div>)}
              </div>)}
            </div>
          </div>
        </div>
      </div>
    </Root>
  );
}
