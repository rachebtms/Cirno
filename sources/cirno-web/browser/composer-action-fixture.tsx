import { useState } from "react";
import { useTheme } from "@/hooks/useTheme";
import { ThreadComposer } from "@/components/thread/ThreadComposer";

export function ComposerActionFixture({ parameters }: { parameters: URLSearchParams }) {
  const { toggle } = useTheme();
  const [preset, setPreset] = useState("preview");
  const [running, setRunning] = useState(false);
  const [stopRequested, setStopRequested] = useState(false);
  return <main className="mx-auto w-full max-w-5xl px-4 pt-24">
    <ThreadComposer
      variant={parameters.get("composerVariant") === "thread" ? "thread" : "hero"}
      modelLabel={preset === "preview" ? "Preview" : "Analysis"}
      modelDetail={preset === "preview" ? "research-small" : "research-large"}
      modelProviderLabel="Research provider"
      modelPreset={parameters.has("models") ? preset : null}
      modelPresets={parameters.has("models") ? [{ id: "preview", name: "Preview", model: "research-small" }, { id: "analysis", name: "Analysis", model: "research-large" }] : []}
      onModelPresetChange={parameters.has("models") ? setPreset : undefined}
      goalState={parameters.has("goal") ? { active: true, objective: "Keep the work in focus." } : undefined}
      isStreaming={running}
      onSend={() => { setStopRequested(false); setRunning(true); }}
      onStop={() => setStopRequested(true)}
    />
    <div className="mt-6 flex gap-4 text-sm">
      <output aria-label="Execution status">{stopRequested ? "Stop requested" : running ? "Working" : "Idle"}</output>
      <button onClick={() => { setRunning(false); setStopRequested(false); }}>Finish response</button>
      <button onClick={toggle}>Toggle theme</button>
    </div>
  </main>;
}
