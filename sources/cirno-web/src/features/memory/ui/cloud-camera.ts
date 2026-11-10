import type { ForceGraph3DInstance } from "3d-force-graph";
import type { CloudLink, CloudNode } from "../model/cloud";

/** Fit the whole 3D sphere in the narrower field of view, including split/mobile panes. */
export function fitMemoryCloud(graph: ForceGraph3DInstance<CloudNode, CloudLink>, nodes: CloudNode[]) {
  const positioned = nodes.filter(node => Number.isFinite(node.x) && Number.isFinite(node.y) && Number.isFinite(node.z));
  if (!positioned.length) return;
  const xs = positioned.map(node => node.x!), ys = positioned.map(node => node.y!), zs = positioned.map(node => node.z!);
  const center = { x: (Math.min(...xs) + Math.max(...xs)) / 2,
    y: (Math.min(...ys) + Math.max(...ys)) / 2, z: (Math.min(...zs) + Math.max(...zs)) / 2 };
  const radius = Math.max(15, ...positioned.map(node => Math.hypot(node.x! - center.x, node.y! - center.y, node.z! - center.z) + 8));
  const camera = graph.camera() as unknown as { fov: number };
  const halfFov = Math.atan(Math.tan(camera.fov * Math.PI / 360) * Math.min(1, graph.width() / graph.height()));
  const distance = radius / Math.sin(halfFov) * 1.2;
  graph.cameraPosition({ x: center.x, y: center.y, z: center.z + distance }, center, 0);
}
