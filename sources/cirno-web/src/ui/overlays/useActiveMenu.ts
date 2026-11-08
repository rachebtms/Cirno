import { useCallback, useEffect, useState } from "react";

/** Menus dismiss when their pane hides; drafts use their own retained editor state. */
export function useActiveMenu(active: boolean, owner: unknown) {
  const [state, setState] = useState({ owner, open: false });
  useEffect(() => { if (!active) setState({ owner, open: false }); }, [active, owner]);
  const onOpenChange = useCallback((open: boolean) => setState({ owner, open: active && open }), [active, owner]);
  return { isOpen: active && state.owner === owner && state.open, onOpenChange };
}
