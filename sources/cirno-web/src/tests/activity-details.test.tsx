import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it } from "vitest";
import { ReasoningRow } from "@/components/thread/activity/ReasoningRow";
import { ActivityStep } from "@/components/thread/activity/ActivityStep";
import { DEFAULT_LOCAL_PREFS, readLocalPreferences, writeLocalPreferences } from "@/lib/local-preferences";
import { setAppLanguage } from "@/i18n";
beforeEach(async () => { localStorage.clear(); await setAppLanguage("en"); });
afterEach(cleanup);
it("allows a brief reasoning row to expand its complete multiline text", () => {
  const text = "First line\nSecond line\n" + "Full detail. ".repeat(60);
  render(<ReasoningRow text={text} streaming={false} />);
  expect(screen.queryByTestId("activity-step-details")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Expand step" }));
  expect(screen.getByTestId("activity-step-details").textContent).toBe(text);
});
it("keeps reasoning and tool detail preferences independent and persistent", () => {
  writeLocalPreferences({ ...DEFAULT_LOCAL_PREFS, reasoningDetailMode: "detailed", toolDetailMode: "brief" });
  expect(readLocalPreferences().reasoningDetailMode).toBe("detailed");
  const view = render(<><ReasoningRow text="First line\nSecond line" streaming={false} /><ActivityStep label="Tool summary" detail="Line one\nLine two" /></>);
  expect(screen.getAllByTestId("activity-step-details")).toHaveLength(1);
  view.unmount();
  writeLocalPreferences({ ...DEFAULT_LOCAL_PREFS, reasoningDetailMode: "brief", toolDetailMode: "detailed" });
  render(<><ReasoningRow text="First line\nSecond line" streaming={false} /><ActivityStep label="Tool summary" detail="Line one\nLine two" /></>);
  expect(screen.getAllByTestId("activity-step-details")).toHaveLength(1);
  expect(screen.getByTestId("activity-step-details")).toHaveTextContent("Tool summary");
});
