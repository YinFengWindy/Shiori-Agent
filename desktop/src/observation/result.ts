import type {
  CapturedObservationFrame,
  ObservationResult,
  ObservationRisk,
} from "./types.js";

const observationRiskSignals = new Set<ObservationRisk>([
  "sensitive",
  "credential",
  "payment",
  "destructive",
  "security_warning",
  "prompt_injection",
]);

/** Validates bridge output against the exact frame that produced it. */
export function parseObservationResult(
  payload: Record<string, unknown>,
  frame: CapturedObservationFrame,
): ObservationResult {
  const requiredString = (key: string): string => {
    const value = payload[key];
    if (typeof value !== "string") throw new Error(`观察结果缺少 ${key}`);
    return value;
  };
  const requiredNumber = (key: string): number => {
    const value = payload[key];
    if (typeof value !== "number" || !Number.isFinite(value)) throw new Error(`观察结果缺少 ${key}`);
    return value;
  };
  const frameId = requiredString("frame_id");
  const capturedAt = requiredString("captured_at");
  const width = requiredNumber("width");
  const height = requiredNumber("height");
  const scaleFactor = requiredNumber("scale_factor");
  if (
    frameId !== frame.frameId
    || capturedAt !== frame.capturedAt
    || width !== frame.width
    || height !== frame.height
    || scaleFactor !== frame.scaleFactor
  ) {
    throw new Error("观察结果与请求帧不一致");
  }
  if (!Array.isArray(payload.targets) || !Array.isArray(payload.risks)) {
    throw new Error("观察结果结构无效");
  }
  const targets = payload.targets.map((item) => {
    if (!item || typeof item !== "object") throw new Error("观察目标结构无效");
    const target = item as Record<string, unknown>;
    if (
      typeof target.label !== "string"
      || typeof target.x !== "number"
      || typeof target.y !== "number"
      || typeof target.confidence !== "number"
      || !Number.isFinite(target.x)
      || !Number.isFinite(target.y)
      || !Number.isFinite(target.confidence)
      || target.x < 0
      || target.x > width
      || target.y < 0
      || target.y > height
      || target.confidence < 0
      || target.confidence > 1
    ) throw new Error("观察目标结构无效");
    return {
      label: target.label,
      x: target.x,
      y: target.y,
      confidence: target.confidence,
    };
  });
  const risks = payload.risks.map((risk) => {
    if (typeof risk !== "string" || !observationRiskSignals.has(risk as ObservationRisk)) {
      throw new Error("观察风险结构无效");
    }
    return risk as ObservationRisk;
  });
  const bubble = requiredString("bubble");
  const experienceCandidate = requiredString("experience_candidate");
  if (bubble.length > 120 || experienceCandidate.length > 280) {
    throw new Error("观察结果文本超过长度限制");
  }
  return {
    frameId,
    capturedAt,
    width,
    height,
    scaleFactor,
    interfaceSummary: requiredString("interface_summary"),
    activityKey: requiredString("activity_key"),
    targets,
    risks,
    bubble,
    experienceCandidate,
  };
}

/** Accepts only the exact host-owned request for one fresh screenshot. */
export function isScreenshotObservationRequest(payload: Record<string, unknown>): boolean {
  return Object.keys(payload).length === 1 && payload.request === "screenshot";
}
