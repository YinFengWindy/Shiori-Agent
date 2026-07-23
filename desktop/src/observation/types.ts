export type ObservationStatus = "off" | "observing" | "reviewing" | "paused" | "failed";

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
