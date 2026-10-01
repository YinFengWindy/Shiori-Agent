import { appendFileSync, mkdirSync } from "node:fs";
import { resolve } from "node:path";
import { app, shell } from "electron";

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

/** Opens only the application-owned directory containing desktop-diagnostics.log. */
export async function openDiagnosticsFolder(): Promise<void> {
  const directory = app.getPath("userData");
  mkdirSync(directory, { recursive: true });
  const error = await shell.openPath(directory);
  if (error) throw new Error(error);
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
