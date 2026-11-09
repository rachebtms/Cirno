/** WebKit can report fractional scale noise even without user zoom. */
export function isViewportZoomed(viewport: VisualViewport): boolean {
  return Math.abs(viewport.scale - 1) > 0.01;
}
