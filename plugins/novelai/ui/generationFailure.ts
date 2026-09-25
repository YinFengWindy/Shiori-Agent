import { BridgeError } from "../../../apps/desktop/renderer/src/shared/bridgeInvoke";
import type { PluginPersona } from "../../../apps/desktop/renderer/src/plugins/pluginHostFeedback";

/** Which kind of problem stopped a generation; decides copy and the offered next step. */
export type GenerationFailureKind =
  | "not-configured"
  | "unauthorized"
  | "quota"
  | "network"
  | "upstream"
  | "invalid"
  | "unavailable"
  | "unknown";

/** A generation failure ready for display: a short title, the cause, and whether settings can fix it. */
export type GenerationFailure = {
  kind: GenerationFailureKind;
  title: string;
  /** The backend's own explanation, already free of secrets; may be empty. */
  message: string;
  /** Whether the plugin's settings tab is the place to fix it (token problems). */
  opensSettings: boolean;
};

/** Token readiness as reported by `plugin.novelai.status` before any generation is attempted. */
export type NovelAiReadiness = {
  configured: boolean;
  /** `missing` (empty) or `placeholder` (an unset `${ENV}` reference); empty when configured. */
  reason: "" | "missing" | "placeholder";
  message: string;
};

// Stable codes raised by the plugin backend (see backend/failures.py).
const kindByCode: Record<string, GenerationFailureKind> = {
  novelai_not_configured: "not-configured",
  novelai_unauthorized: "unauthorized",
  novelai_quota: "quota",
  novelai_network: "network",
  novelai_upstream: "upstream",
  invalid_request: "invalid",
  plugin_unavailable: "unavailable",
};

const titleByKind: Record<GenerationFailureKind, string> = {
  "not-configured": "NovelAI 未配置",
  unauthorized: "NovelAI token 无效",
  quota: "NovelAI 额度不足",
  network: "连不上 NovelAI",
  upstream: "NovelAI 返回了错误",
  invalid: "请求参数有误",
  unavailable: "生图插件暂不可用",
  unknown: "生成失败",
};

// Defense in depth: the backend already scrubs the token, but a bearer header or
// a NovelAI persistent token ("pst-…") must never reach the screen or a toast.
const secretPatterns = [/Bearer\s+[^\s"',;]+/gi, /\bpst-[A-Za-z0-9_-]{6,}/g];

/** Masks anything that looks like a credential in a message bound for the UI. */
export function scrubSecrets(text: string): string {
  return secretPatterns.reduce((current, pattern) => current.replace(pattern, (match) => (
    match.toLowerCase().startsWith("bearer") ? "Bearer ***" : "***"
  )), text);
}

/** Classifies a failed `generate` call by its bridge error code. */
export function describeGenerationFailure(error: unknown): GenerationFailure {
  const code = error instanceof BridgeError ? error.code : "";
  const kind = kindByCode[code] ?? "unknown";
  const raw = error instanceof Error ? error.message : String(error ?? "");
  const message = scrubSecrets(raw.trim());
  return {
    kind,
    title: titleByKind[kind],
    // The title already says everything a bare "未配置" message would.
    message: message === titleByKind[kind] ? "" : message,
    opensSettings: kind === "not-configured" || kind === "unauthorized",
  };
}

/** The failure a not-yet-configured plugin should show before anyone presses 生成. */
export function failureFromReadiness(readiness: NovelAiReadiness | null): GenerationFailure | null {
  if (!readiness || readiness.configured) return null;
  return {
    kind: "not-configured",
    title: titleByKind["not-configured"],
    message: readiness.message === titleByKind["not-configured"] ? "" : readiness.message,
    opensSettings: true,
  };
}

/**
 * Which host persona scene fronts a failure (runtime API 2.4.0): the kinds
 * that come from the backend's stable error codes name their scene, the
 * rest take the generic line. The words themselves are the host's.
 */
const personaByKind: Record<GenerationFailureKind, PluginPersona> = {
  "not-configured": "not_configured",
  unauthorized: "unauthorized",
  quota: "quota",
  network: "network",
  upstream: "upstream",
  invalid: true,
  unavailable: true,
  unknown: true,
};

/** The `persona` a failure's card and toast ask the host for. */
export function failurePersona(failure: GenerationFailure): PluginPersona {
  return personaByKind[failure.kind];
}
