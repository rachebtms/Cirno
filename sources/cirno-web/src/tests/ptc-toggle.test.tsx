import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ThreadHeader } from "@/components/thread/ThreadHeader";
import i18n from "@/i18n";

describe("PTC conversation option", () => {
  it("offers an accessible creation toggle next to temporary chat without changing that option", async () => {
    await i18n.changeLanguage("en");
    const onPtc = vi.fn();
    const onTemporary = vi.fn();
    render(<ThreadHeader title="New conversation" theme="dark" onToggleTheme={vi.fn()} onToggleSidebar={vi.fn()}
      ptcModeEnabled={false} onPtcModeEnabledChange={onPtc}
      temporaryChatEnabled={false} onTemporaryChatEnabledChange={onTemporary} />);
    const toggle = screen.getByRole("button", { name: "PTC mode" });
    expect(toggle).toHaveAttribute("aria-pressed", "false");
    fireEvent.click(toggle);
    expect(onPtc).toHaveBeenCalledWith(true);
    expect(onTemporary).not.toHaveBeenCalled();
  });
});
