import { useEffect, useState } from "react";
export function usePinClock(expiresAt: number) {
  const [now, setNow] = useState(Date.now);
  useEffect(() => {
    setNow(Date.now());
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [expiresAt]);
  return Math.max(0, Math.ceil((expiresAt - now) / 1000));
}
