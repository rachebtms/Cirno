export function normalizeTools(tools: readonly string[]): string[] {
  return tools.includes("*") ? ["*"] : [...tools].sort((left, right) => left.localeCompare(right));
}
export function displayToolName(tool: string, server: string): string {
  const prefix = `mcp_${server}_`;
  return tool.startsWith(prefix) ? tool.slice(prefix.length) : tool;
}
export function formatTransport(transport: string): string {
  return ({ streamableHttp: "Streamable HTTP", stdio: "STDIO", sse: "SSE" } as Record<string, string>)[transport] ?? transport;
}
