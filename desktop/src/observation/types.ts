export type ObservationStatus = "off" | "observing" | "reviewing" | "paused" | "failed";

export type PetObservationPayload = {
  status: ObservationStatus;
  enabled: boolean;
  bubble: string;
  persistent: boolean;
};
