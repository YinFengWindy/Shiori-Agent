/** Public MCP settings/status projection. Secrets are write-only. */
export type McpServer = {
  id: string; label: string; revision: number; enabled: boolean;
  transport: { kind: "stdio"; cwd: string | null };
  command_configured: boolean; env_names: string[];
  selection: { mode: "all" | "selected"; names: string[] };
  status: string; error: string | null;
  tools: Array<{ name: string; description: string }>;
  operation: { id: string; kind: string; status: string; error: string | null } | null;
};
/** Snapshot returned by reads and short mutations. */
export type McpSnapshot = { instance_id: string; servers: McpServer[]; error: string | null; loading: boolean };
