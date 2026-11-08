import { resolve } from "node:path";
import { expect, it } from "vitest";

import { componentInventory } from "@/dev/gallery/inventory-plugin";

it("indexes the current frontend and channel source layout and resolves component consumers", () => {
  const root = resolve(process.cwd(), "../..");
  const inventory = componentInventory(root);
  const activity = inventory.find((entry) => entry.path === "sources/cirno-web/src/components/thread/AgentActivityCluster.tsx");
  expect(activity?.exports).toContain("AgentActivityCluster");
  expect(activity?.usedBy).toContain("sources/cirno-web/src/components/thread/ThreadMessages.tsx");
  const disclosure = inventory.find((entry) => entry.path.endsWith("/activity/ActivityDisclosure.tsx"));
  expect(disclosure?.usedBy).toContain(activity?.path);
  expect(inventory.some((entry) => entry.group === "Channels / websocket")).toBe(true);
});
