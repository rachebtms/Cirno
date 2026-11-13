import { Button, Tooltip } from "@heroui/react";
import { Maximize2, Scan } from "lucide-react";
import { useEffect, useMemo, useRef, useState, type Ref } from "react";
import { useTranslation } from "react-i18next";
import type { ForceGraph3DInstance } from "3d-force-graph";
import type { MemoryLink, MemoryRecord } from "@/lib/contracts/memory";
import { InlineError } from "@/ui/feedback/InlineError";
import { MEMORY_COLORS, memoryCloud, type CloudLink, type CloudNode } from "../model/cloud";
import { memoryTitle } from "../model/presentation";
import { fitMemoryCloud } from "./cloud-camera";

const EMPTY_LINKS: MemoryLink[] = [];
export interface MemoryCloudProps {
  records: MemoryRecord[]; links?: MemoryLink[]; active: boolean; loading?: boolean;
  onInspect: (record: MemoryRecord) => void; onTag: (tag: string) => void;
}
export function MemoryCloudScene({ records, links = EMPTY_LINKS, active, loading = false, onInspect, onTag, onExpand, expandRef }: MemoryCloudProps & {
  onExpand?: () => void; expandRef?: Ref<HTMLButtonElement>;
}) {
  const { t } = useTranslation();
  const host = useRef<HTMLDivElement>(null);
  const graph = useRef<ForceGraph3DInstance<CloudNode, CloudLink> | null>(null);
  const callbacks = useRef({ onInspect, onTag, active });
  callbacks.current = { onInspect, onTag, active };
  const model = useMemo(() => memoryCloud(records, links), [records, links]);
  const [error, setError] = useState<string | null>(null);
  const [ready, setReady] = useState(false);
  useEffect(() => {
    const element = host.current;
    if (!element || !model.nodes.length) return;
    let cancelled = false;
    let instance: ForceGraph3DInstance<CloudNode, CloudLink> | null = null;
    let resize: ResizeObserver | null = null;
    let theme: MutationObserver | null = null;
    setError(null);
    setReady(false);
    const visible = () => {
      if (!instance) return;
      if (callbacks.current.active && !document.hidden) instance.resumeAnimation();
      else instance.pauseAnimation();
    };
    void import("3d-force-graph").then(({ default: ForceGraph3D }) => {
      if (cancelled) return;
      instance = new ForceGraph3D(element, {
        controlType: "orbit", rendererConfig: { antialias: true, powerPreference: "low-power" },
      }) as unknown as ForceGraph3DInstance<CloudNode, CloudLink>;
      graph.current = instance;
      const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
      let settled = false;
      instance.showNavInfo(false).nodeId("id").nodeColor(node => node.color)
        .nodeVal(node => node.tag ? 1.3 : 3).nodeRelSize(3).nodeResolution(12)
        .nodeLabel(node => {
          const label = document.createElement("span");
          label.textContent = node.memory ? memoryTitle(node.memory, t) : node.label;
          return label;
        })
        .linkLabel(link => {
          const label = document.createElement("span");
          label.textContent = t(`memoryGraph.relation_${link.relation}`, { defaultValue: link.relation });
          return label;
        })
        .linkWidth(link => link.relation === "tag" ? 0.35 : 1)
        .linkOpacity(0.35).linkDirectionalArrowLength(link => link.relation === "tag" ? 0 : 3)
        .cooldownTicks(reduced ? 0 : 30).warmupTicks(reduced ? 100 : 80)
        .onNodeClick(node => {
          if (node.memory) callbacks.current.onInspect(node.memory);
          else if (node.tag) callbacks.current.onTag(node.tag);
        })
        .onEngineTick(() => {
          if (!settled && instance) fitMemoryCloud(instance, model.nodes);
        })
        .onEngineStop(() => {
          if (!settled && instance) { fitMemoryCloud(instance, model.nodes); settled = true; }
        })
        .graphData(model);
      const updateSize = () => {
        if (!instance) return;
        const bounds = element.getBoundingClientRect();
        instance.width(Math.max(1, bounds.width)).height(Math.max(1, bounds.height));
        if (bounds.width > 0 && bounds.height > 0) fitMemoryCloud(instance, model.nodes);
      };
      const updateTheme = () => instance?.backgroundColor(getComputedStyle(element).backgroundColor);
      updateSize(); updateTheme(); visible();
      resize = new ResizeObserver(updateSize); resize.observe(element);
      theme = new MutationObserver(updateTheme);
      theme.observe(document.documentElement, { attributes: true, attributeFilter: ["class", "style", "data-theme"] });
      document.addEventListener("visibilitychange", visible);
      setReady(true);
    }).catch(reason => {
      if (!cancelled) setError(reason instanceof Error ? reason.message : String(reason));
    });
    return () => {
      cancelled = true;
      resize?.disconnect(); theme?.disconnect();
      document.removeEventListener("visibilitychange", visible);
      instance?._destructor();
      if (graph.current === instance) graph.current = null;
      element.replaceChildren();
    };
  }, [model, t]);
  useEffect(() => {
    if (active && !document.hidden) graph.current?.resumeAnimation();
    else graph.current?.pauseAnimation();
  }, [active]);
  return <section className="memory-cloud" aria-label={t("memoryGraph.cloud")}>
    <div className="memory-cloud-scene" ref={host} role="img" aria-label={t("memoryGraph.cloudDescription")} />
    <div className="memory-cloud-toolbar">
      <span>{t("memoryGraph.nodeCount", { count: records.length })}</span>
      <div className="memory-cloud-actions">
      <Tooltip><Button variant="secondary" isIconOnly size="sm" aria-label={t("memoryGraph.fit")} isDisabled={!ready || !records.length}
        onPress={() => { if (graph.current) fitMemoryCloud(graph.current, model.nodes); }}><Scan size={16} /></Button>
        <Tooltip.Content>{t("memoryGraph.fit")}</Tooltip.Content></Tooltip>
      {onExpand && <Tooltip><Button ref={expandRef} variant="secondary" isIconOnly size="sm" aria-label={t("memoryGraph.expand")}
        isDisabled={!records.length} onPress={onExpand}><Maximize2 size={16} /></Button>
        <Tooltip.Content>{t("memoryGraph.expand")}</Tooltip.Content></Tooltip>}
      </div>
    </div>
    {!error && (loading || (records.length > 0 && !ready)) && <p className="memory-cloud-empty" role="status">{t("memoryGraph.loading")}</p>}
    {!loading && !records.length && <p className="memory-cloud-empty">{t("features.noMemorySources")}</p>}
    {error && <div className="memory-cloud-error"><p>{t("memoryGraph.renderError")}</p><InlineError message={error} /></div>}
    <div className="memory-cloud-footer">
    <div className="memory-cloud-legend">{Object.entries(MEMORY_COLORS).map(([layer, color]) =>
      <span key={layer}><i style={{ background: color }} />{t(`memoryLibrary.${layer}`)}</span>)}
      <span><i style={{ background: "#91a1a7" }} />{t("memoryGraph.relation_tag")}</span></div>
    <p className="memory-cloud-help">{t("memoryGraph.gestureHelp")}</p>
    </div>
  </section>;
}
