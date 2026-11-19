import { expect, it } from "vitest";
import { webSearchRunsByTraceLine } from "@/components/thread/activity/web-search-model";

it("retains ordinary fc/fd DNS search sources while filtering local URL spellings", () => {
  const runs = webSearchRunsByTraceLine([{ phase: "end", call_id: "fixture", name: "web__search", arguments: { query: "fixture" },
    result: { results: [
      { title: "Public docs", url: "https://fcdn.example.org/docs?token=private" },
      { title: "Other docs", url: "https://fd-tools.example.org/docs" },
      { title: "Private", url: "http://localhost.:3000/private" },
      { title: "Link-local", url: "http://[fe90::1]/private" },
    ] } }]);
  expect([...runs.values()][0].sources.map(source => source.href)).toEqual([
    "https://fcdn.example.org/docs", "https://fd-tools.example.org/docs",
  ]);
});
