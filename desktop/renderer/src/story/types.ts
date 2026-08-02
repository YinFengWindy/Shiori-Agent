/** A Story item shown in the library. */
export type StorySummary = {
  story_id: string;
  title: string;
  status: "active" | "archived" | "deleting";
  created_at: string;
};

/** One committed text presentation cue. */
export type StoryCue = {
  id: string;
  beat_id: string;
  story_id: string;
  text: string;
  kind: "dialogue" | "action" | "narration";
  speaker: string | null;
};

/** Durable Story input and generation receipt. */
export type StoryTurn = {
  id: string;
  kind: "opening" | "player" | "continue";
  input: string;
  status: "pending" | "generating" | "validating" | "committed" | "failed" | "cancelled";
  committedBeatIds: string[];
};

/** Renderer-safe Story state returned by the bridge. */
export type StoryDetails = {
  id: string;
  title: string;
  background: string;
  status: string;
  revision: number;
  roleSnapshot: { id?: string; name?: string };
  playerProfile: { display_name: string; appearance: string; identity: string };
  segment: { operation: string; status: string };
  cues: StoryCue[];
  turns: StoryTurn[];
};

/** Player-authored fields required to begin a Story. */
export type StoryCreationInput = {
  title: string;
  background: string;
  startsAt: string;
  roleId: string;
  playerProfile: {
    displayName: string;
    appearance: string;
    identity: string;
  };
};

/** Stable bridge failure surfaced by the Story client. */
export class StoryBridgeError extends Error {
  constructor(message: string, readonly code: string) {
    super(message);
    this.name = "StoryBridgeError";
  }
}
