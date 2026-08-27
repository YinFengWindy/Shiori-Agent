import { appendFileSync, mkdirSync } from "node:fs";
import { resolve } from "node:path";
import { app } from "electron";

type DiagnosticScope = "main" | "renderer";

type DiagnosticEntry = {
  scope: DiagnosticScope;
  event: string;
  payload: Record<string, unknown>;
};

const desktopDiagnosticsLogName = "desktop-diagnostics.log";

function safeJsonStringify(value: unknown): string {
  const seen = new WeakSet<object>();
  return JSON.stringify(value, (_key, currentValue) => {
    if (currentValue instanceof Error) {
      return {
        name: currentValue.name,
        message: currentValue.message,
        stack: currentValue.stack,
      };
    }
    if (typeof currentValue === "object" && currentValue !== null) {
      if (seen.has(currentValue)) {
        return "[circular]";
      }
      seen.add(currentValue);
    }
    return currentValue;
  });
}

function getDiagnosticsLogPath(): string {
  const userDataDir = app.getPath("userData");
  mkdirSync(userDataDir, { recursive: true });
  return resolve(userDataDir, desktopDiagnosticsLogName);
}

/** Appends one structured desktop diagnostic row so renderer crashes stay inspectable after white screens. */
export function logDesktopDiagnostic(entry: DiagnosticEntry): void {
  const line = `${safeJsonStringify({
    timestamp: new Date().toISOString(),
    ...entry,
  })}\n`;
  const logPath = getDiagnosticsLogPath();
  appendFileSync(logPath, line, { encoding: "utf-8" });
}
