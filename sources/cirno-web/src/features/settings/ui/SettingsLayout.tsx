import type { ReactNode, Ref } from "react";
import "./settings-layout.css";

export function SettingsLayout({ navigation, section, title, contentRef, children, overlays }: {
  navigation?: ReactNode;
  section: string;
  title?: string;
  contentRef?: Ref<HTMLElement>;
  children: ReactNode;
  overlays?: ReactNode;
}) {
  return <div className="settings-workspace">
    {navigation}
    <div className="settings-content-scroll">
      <section key={section} ref={contentRef} className="settings-content" data-settings-section={section} data-testid="settings-section-transition">
        {title && <header className={navigation ? "settings-content-heading settings-heading-with-navigation" : "settings-content-heading"}><h1>{title}</h1></header>}
        {children}
      </section>
    </div>{overlays}
  </div>;
}
