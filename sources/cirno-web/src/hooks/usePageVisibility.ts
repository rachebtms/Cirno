import { createContext, useContext, useEffect, useState } from "react";

export const SurfaceVisibilityContext = createContext(true);

function pageIsVisible(): boolean {
  return typeof document === "undefined" || document.visibilityState !== "hidden";
}

/** Keep background tabs quiet while resuming work immediately on return. */
export function usePageVisibility(): boolean {
  const surfaceVisible = useContext(SurfaceVisibilityContext);
  const [visible, setVisible] = useState(pageIsVisible);

  useEffect(() => {
    const update = () => setVisible(pageIsVisible());
    document.addEventListener("visibilitychange", update);
    return () => document.removeEventListener("visibilitychange", update);
  }, []);

  return visible && surfaceVisible;
}
