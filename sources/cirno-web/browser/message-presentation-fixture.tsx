import { useTranslation } from "react-i18next";
import { MessageActions, MessageBubble } from "@/features/messages";
import { useTheme } from "@/hooks/useTheme";
import type { UIMessage } from "@/lib/contracts/messages";
import sampleVideo from "@/dev/gallery/fixtures/sample.webm";

const plot = `data:image/svg+xml,${encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="640" height="360"><rect width="640" height="360" fill="#e2f3f9"/><path d="M40 300L180 220L320 250L460 100L600 50" stroke="#167da3" stroke-width="8" fill="none"/></svg>')}`;
const traces = Array.from(
  { length: 10_000 },
  (_, index) =>
    `nodes.execute #${index}\npython research.py --checkpoint ${index}`,
);

export function MessagePresentationFixture() {
  useTheme();
  const { i18n } = useTranslation(),
    zh = i18n.language.startsWith("zh");
  const uploaded: UIMessage = {
    id: "mixed",
    role: "user",
    createdAt: 1_800_000_000_000,
    content: zh ? "核对这些实验结果。" : "Check these experiment results.",
    images: [{ name: "plot.svg", url: plot }],
    media: [
      { kind: "image", name: "plot.svg", url: plot },
      {
        kind: "file",
        name: "measurements.csv",
        url: "data:text/csv,x%2Cy%0A1%2C2",
      },
      { kind: "video", name: "experiment.webm", url: sampleVideo },
    ],
  };
  const answer: UIMessage = {
    id: "reply",
    role: "assistant",
    createdAt: uploaded.createdAt + 1000,
    completedAt: uploaded.createdAt + 6000,
    content: zh
      ? "已保留图像、测量表和实验视频，供核对。"
      : "The plot, measurements and experiment video are available for review.",
    responseSources: [
      {
        provider: "custom",
        model: "research-model",
        preset: "Research backup",
        fallback: true,
      },
    ],
  };
  return (
    <main className="mx-auto max-w-3xl space-y-8 p-4 sm:p-8">
      <section aria-label="Mixed attachments">
        <MessageBubble message={uploaded} />
        <MessageActions message={uploaded} onEdit={() => {}} />
      </section>
      <section aria-label="Assistant reply">
        <MessageBubble message={answer} />
        <MessageActions message={answer} onForkFromHere={() => {}} />
      </section>
      <section aria-label="Delivery failure">
        <MessageBubble
          message={{
            id: "failed",
            role: "user",
            content: zh ? "未送达的消息" : "Unsent message",
            createdAt: 1,
            deliveryStatus: "failed",
            deliveryErrorKind: "message_too_big",
          }}
        />
      </section>
      <section aria-label="System input">
        <MessageBubble
          message={{
            id: "heartbeat",
            role: "user",
            content: "Inspect authorized research tasks.",
            createdAt: 1,
            inputOrigin: { kind: "heartbeat", label: "Heartbeat" },
          }}
        />
      </section>
      <section aria-label="Large tool history">
        <MessageBubble
          message={{
            id: "tools",
            role: "tool",
            kind: "trace",
            content: traces[0],
            traces,
            createdAt: 1,
          }}
        />
      </section>
    </main>
  );
}
