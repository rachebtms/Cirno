/** Happy DOM emits hashchange for pushState/replaceState; browsers do not. */
export function installHistoryEvents(): void {
  const writes: { oldURL: string; newURL: string }[] = [];
  for (const method of ["pushState", "replaceState"] as const) {
    const original = window.history[method].bind(window.history);
    window.history[method] = (...args: Parameters<History[typeof method]>) => {
      const oldURL = window.location.href;
      original(args[0], args[1], args[2]);
      const newURL = window.location.href;
      if (new URL(oldURL).hash !== new URL(newURL).hash) {
        writes.push({ oldURL, newURL });
      }
    };
  }
  window.addEventListener("hashchange", (event) => {
    const index = writes.findIndex(write =>
      write.oldURL === event.oldURL && write.newURL === event.newURL);
    if (index < 0) return;
    writes.splice(index, 1);
    event.stopImmediatePropagation();
  }, true);
}
