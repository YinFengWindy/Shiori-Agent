/**
 * Error thrown when a bridge call returns an error envelope; carries the
 * envelope's stable `code` and optional structured `details` next to the
 * human-readable message. Domain clients (`pluginBridgeClient.ts`,
 * `storyBridgeClient.ts`, ...) subclass it so `instanceof` checks stay scoped
 * to their own domain while sharing one implementation of that shape.
 */
export class BridgeError extends Error {
  constructor(
    message: string,
    readonly code: string,
    readonly details?: Record<string, unknown>,
  ) {
    super(message);
    this.name = "BridgeError";
  }
}

/**
 * Stable error shared by plugin management, a plugin's own RPCs and
 * cooperative peers. Plugins match it with `instanceof`, which only works
 * because the host and every plugin see this single class: built-in plugins
 * compile against it and external plugins receive it as a host peer.
 * A locally disposed communication context reports `plugin_unavailable` with
 * `details.reason === "context_disposed"`; other unavailable errors do not imply disposal.
 */
export class PluginBridgeError extends BridgeError {
  constructor(message: string, code: string, details?: Record<string, unknown>) {
    super(message, code, details);
    this.name = "PluginBridgeError";
  }
}

/** Normalizes a thrown value; includeDetail preserves RPC diagnostics for a disclosure or diagnostic sink. */
export function errorMessage(error: unknown, options?: { includeDetail?: boolean }): string {
  const message = typeof error === "object" && error !== null && "message" in error && typeof error.message === "string" ? error.message : String(error ?? "");
  const summary = scrubErrorDetail(message).replace(/^Error invoking remote method [^\n]+?: (?:Error: )?/, "").replace(/^(?:[A-Za-z]+Error:\s*)+/, "");
  return options?.includeDetail ? [summary, errorDiagnosticDetail(error)].filter(Boolean).join("\n") : summary;
}

function errorDiagnosticDetail(error: unknown) {
  const details = typeof error === "object" && error !== null && "details" in error ? error.details : null;
  return typeof details === "object" && details !== null && "detail" in details && typeof details.detail === "string" ? scrubErrorDetail(details.detail) : "";
}

/** Redacts credential-shaped text before any error reaches UI or copied diagnostics. */
export function scrubErrorDetail(text: string): string {
  return text
    .replace(/([?&]key=)[^&\s"']+/gi, "$1***")
    .replace(/Bearer\s+[^\s"',;]+/gi, "Bearer ***")
    .replace(/\b(?:sk-|pst-)[A-Za-z0-9_-]{6,}/g, "***")
    .replace(/((?:[?&]|\b)(?:api[_-]?key|access[_-]?token|token|secret|password|signature)["']?\s*[=:]\s*["']?)[^\s&"',;}]+/gi, "$1***");
}

/** Short operation summary plus scrubbed technical context for a detail disclosure. */
export function errorFeedback(error: unknown, fallback = "操作未完成，请重试") {
  const envelope = typeof error === "object" && error !== null && "message" in error && typeof error.message === "string" ? error : null;
  const raw = errorMessage(envelope ? envelope.message : error).trim();
  const lines = raw.split(/\r?\n/);
  const first = lines[0] ?? "";
  const technical = /(?:[A-Za-z]+Error:|Traceback|https?:\/\/|[A-Z]:\\|\*\*\*)/.test(first);
  // A short, readable domain validation message remains actionable. Legacy
  // transport exceptions are kept only in details, even when detail already exists.
  const readable = /[一-龥]/.test(first) && first.length <= 180 && !technical;
  const message = readable ? first : fallback;
  const reported = errorDiagnosticDetail(error);
  const detail = scrubErrorDetail([...(message === raw ? [] : [raw]), reported].filter(Boolean).join("\n"));
  return { message, detail };
}

/** Adapts structured feedback to legacy text-only state; InlineError splits the first line and details. */
export function errorFeedbackText(error: unknown, fallback?: string) {
  const view = errorFeedback(error, fallback);
  return [view.message, view.detail].filter(Boolean).join("\n");
}
