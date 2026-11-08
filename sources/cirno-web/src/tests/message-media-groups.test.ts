import { expect, it } from "vitest";
import { attachmentGroups } from "@/features/messages/model/attachmentGroups";

it("keeps mixed uploads together and deduplicates images across both message formats", () => {
  const groups = attachmentGroups(
    [
      { kind: "image", name: "plot.png", url: "/plot" },
      { kind: "file", name: "measurements.csv", url: "/table" },
      { kind: "video", name: "experiment.webm", url: "/video" },
    ],
    [{ name: "plot.png", url: "/plot" }],
    new Map(),
  );
  expect(groups.images).toHaveLength(1);
  expect(groups.videos.map((item) => item.url)).toEqual(["/video"]);
  expect(groups.files.map((item) => item.url)).toEqual(["/table"]);
});

it("omits only images actually rendered inline, while preserving missing upload placeholders", () => {
  const groups = attachmentGroups(
    [
      { kind: "image", name: "first.png" },
      { kind: "image", name: "second.png" },
      { kind: "image", name: "inline.png", url: "/inline" },
      { kind: "file", name: "report.pdf", url: "/report" },
    ],
    [],
    new Map([["/inline", 1]]),
  );
  expect(groups.images.map((item) => item.name)).toEqual([
    "first.png",
    "second.png",
  ]);
  expect(groups.files[0].name).toBe("report.pdf");
});

it("uses the file's explicit extension to correct mislabeled media", () => {
  const groups = attachmentGroups(
    [
      { kind: "image", name: "report.html", url: "/report" },
      { kind: "file", name: "figure.svg", url: "/figure" },
    ],
    [],
    new Map(),
  );
  expect(groups.files[0].name).toBe("report.html");
  expect(groups.images[0].name).toBe("figure.svg");
});
