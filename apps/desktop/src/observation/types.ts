/** Lifecycle states that determine the pet's observation presentation. */
export type ObservationStatus = "off" | "observing" | "reviewing" | "paused" | "failed";

/** Main-process payload for the pet renderer's status and optional reply bubble. */
export type PetObservationPayload = {
  status: ObservationStatus;
  enabled: boolean;
  bubble: string;
  persistent: boolean;
};

/** Layout assigned by the main process after measuring a full pet reply bubble. */
export type PetBubbleLayout = {
  placement: "above" | "below";
  height: number;
};
