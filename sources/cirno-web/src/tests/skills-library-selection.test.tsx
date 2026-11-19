import { act, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { SkillsLibrary } from "@/features/skills/SkillsLibrary";
import { ClientProvider } from "@/providers/ClientProvider";
import type { CirnoClient } from "@/lib/cirno-client";
import type { SkillSummary } from "@/lib/contracts/skills";

const captured = vi.hoisted(() => ({ select: null as null | ((skill: SkillSummary) => void), close: null as null | (() => void) }));
vi.mock("@/features/skills/ui/InstalledSkills", () => ({ InstalledSkills: ({ onSelect }: { onSelect: (skill: SkillSummary) => void }) => { captured.select = onSelect; return null; } }));
vi.mock("@/features/skills/ui/SkillDetailDialog", () => ({ SkillDetailDialog: ({ skill, onClose }: { skill: SkillSummary; onClose: () => void }) => { captured.close = onClose; return <div role="status">Detail {skill.name}</div>; } }));
vi.mock("@/features/skills/SkillsMarketplace", () => ({ SkillsMarketplace: () => null }));
vi.mock("@/features/skills/SkillHistory", () => ({ SkillHistory: () => null }));
const first = { name: "first", source: "home", description: "fixture", available: true };
const second = { ...first, name: "second" };
function view(client: CirnoClient) { return <ClientProvider client={client} token="fixture"><SkillsLibrary skills={[first, second]} /></ClientProvider>; }
it("does not reopen a prior detail after switching away from and back to a connection", () => {
  const client = {} as CirnoClient, page = render(view(client));
  act(() => captured.select!(first));
  expect(screen.getByRole("status")).toHaveTextContent("Detail first");
  page.rerender(view({} as CirnoClient));
  page.rerender(view(client));
  expect(screen.queryByRole("status")).not.toBeInTheDocument();
});
it("ignores a retained catalog selection from a retired connection", () => {
  const page = render(view({} as CirnoClient)), old = captured.select!;
  page.rerender(view({} as CirnoClient));
  act(() => captured.select!(second));
  act(() => old(first));
  expect(screen.getByRole("status")).toHaveTextContent("Detail second");
});
it("does not let an earlier detail close a different selected Skill", () => {
  render(view({} as CirnoClient));
  act(() => captured.select!(first));
  const close = captured.close!;
  act(() => captured.select!(second));
  act(() => close());
  expect(screen.getByRole("status")).toHaveTextContent("Detail second");
});
