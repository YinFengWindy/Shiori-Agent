type RendererGlobalError = {
  kind: "error" | "unhandledrejection";
  message: string;
  stack?: string;
  filename?: string;
  lineno?: number;
  colno?: number;
  details?: Record<string, unknown>;
};

function reportRendererGlobalError(payload: RendererGlobalError): void {
  window.miraDesktop.reportRendererDiagnostic(payload);
}

/** Registers process-wide renderer error reporting before React mounts. */
export function registerRendererGlobalDiagnostics(): void {
  window.addEventListener("error", (event) => {
    reportRendererGlobalError({
      kind: "error",
      message: event.message || "renderer error",
      stack: event.error instanceof Error ? event.error.stack : undefined,
      filename: event.filename,
      lineno: event.lineno,
      colno: event.colno,
    });
  });
  window.addEventListener("unhandledrejection", (event) => {
    const reason = event.reason;
    reportRendererGlobalError({
      kind: "unhandledrejection",
      message: reason instanceof Error
        ? reason.message
        : String(reason ?? "renderer unhandled rejection"),
      stack: reason instanceof Error ? reason.stack : undefined,
      details: reason instanceof Error ? {} : { reason },
    });
  });
}
