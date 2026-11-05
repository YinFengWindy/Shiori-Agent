/** Public MCP settings/status projection. Secrets are write-only. */
export type McpServer = {
  id: string; label: string; revision: number; enabled: boolean;
  transport: { kind: "stdio"; cwd: string | null } | { kind: "streamable_http"; auth: "none" | "bearer" | "headers" | "oauth" };
  command_configured: boolean; env_names: string[];
  url_configured: boolean; bearer_configured: boolean; header_names: string[];
  oauth: { status: "login_required" | "logging_in" | "authorized"; redirect_uri: string; client_configured: boolean } | null;
  selection: { mode: "all" | "selected"; names: string[] };
  status: string; error: string | null;
  tools: Array<{ name: string; description: string }>;
  operation: { id: string; kind: string; status: string; error: string | null; authorization_url?: string } | null;
};
/** Snapshot returned by reads and short mutations. */
export type McpSnapshot = { instance_id: string; servers: McpServer[]; error: string | null; loading: boolean };
