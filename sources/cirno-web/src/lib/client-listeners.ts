/** UI observers cannot interrupt transport bookkeeping or other observers. */
export class ClientListeners<Args extends unknown[]> {
  private readonly handlers = new Set<(...args: Args) => void>();
  constructor(private readonly label: string) {}

  get size(): number { return this.handlers.size; }

  subscribe(handler: (...args: Args) => void): () => void {
    this.handlers.add(handler);
    return () => { this.handlers.delete(handler); };
  }

  invoke(handler: (...args: Args) => void, ...args: Args): void {
    try { handler(...args); }
    catch (error) { console.error(`WebSocket ${this.label} listener failed`, error); }
  }

  emit(...args: Args): void {
    for (const handler of this.handlers) this.invoke(handler, ...args);
  }
}
