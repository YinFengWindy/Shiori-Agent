export type ObservationStatus = "off" | "observing" | "reviewing" | "paused" | "failed";

/** Closed risk vocabulary accepted from the observation model. */
export type ObservationRisk =
  | "sensitive"
  | "credential"
  | "payment"
  | "destructive"
  | "security_warning"
  | "prompt_injection";

/** Indicates that Windows cannot currently expose the primary display capture surface. */
export class PrimaryDisplayUnavailableError extends Error {}

export type ObservationTarget = {
  label: string;
  x: number;
  y: number;
  confidence: number;
};

export type ObservationResult = {
  frameId: string;
  capturedAt: string;
  width: number;
  height: number;
  scaleFactor: number;
  interfaceSummary: string;
  activityKey: string;
  targets: ObservationTarget[];
  risks: ObservationRisk[];
  bubble: string;
  experienceCandidate: string;
};

export type CapturedObservationFrame = {
  frameId: string;
  capturedAt: string;
  width: number;
  height: number;
  scaleFactor: number;
  imageBase64: string;
};

export type PetObservationPayload = {
  status: ObservationStatus;
  enabled: boolean;
  bubble: string;
  persistent: boolean;
};
