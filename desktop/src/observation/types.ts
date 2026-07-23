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

/** Indicates that capture was rejected because Windows is currently locked. */
export class ScreenLockedCaptureError extends PrimaryDisplayUnavailableError {}

/** Marks failures originating specifically from acquiring a desktop screenshot. */
export class ScreenCaptureFailedError extends Error {
  readonly cause: unknown;

  constructor(cause: unknown) {
    super(cause instanceof Error ? cause.message : String(cause));
    this.name = "ScreenCaptureFailedError";
    this.cause = cause;
  }
}

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
