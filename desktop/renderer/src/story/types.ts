/** A Story entry shown in the launcher. */
export type StorySummary = {
  storyId: string;
  relativeDbPath: string;
  title: string;
  status: "active" | "archived" | "deleting";
  createdAt: string;
};

/** Story operation state owned by the current segment. */
export type StoryOperation = "idle" | "awaiting_player" | "generating";

/** Persisted Story segment read model. */
export type StorySegment = {
  id: string;
  sequence: number;
  startsAt: string;
  status: string;
  mode: string;
  operation: StoryOperation;
  openingContext: Record<string, unknown>;
  runtimeSnapshot: Record<string, unknown>;
};

/** One committed narrative beat returned by the Story repository. */
export type StoryBeat = {
  id: string;
  storyId: string;
  segmentId: string;
  turnId: string;
  sequence: number;
  effectiveAt: string;
  text: string;
  kind: "dialogue" | "action" | "narration";
  speaker: string | null;
  recordedAt: string;
};

/** One player or opening turn in the Story history. */
export type StoryTurn = {
  id: string;
  kind: "opening" | "player" | "continue";
  input: string;
  status: string;
  attemptId: string | null;
  committedBeatIds: string[];
  error: unknown;
  createdAt: string;
  updatedAt: string;
};

/** A renderer-safe Story read model returned by stories.get and stories.* mutations. */
export type StoryDetails = {
  id: string;
  title: string;
  background: string;
  status: "active" | "archived";
  revision: number;
  roleSnapshot: {
    id?: string;
    name?: string;
    description?: string;
    avatar?: string | null;
  };
  playerProfile: {
    display_name?: string;
    appearance?: string;
    identity?: string;
  };
  segment: StorySegment;
  beats: StoryBeat[];
  cues: Array<Record<string, unknown>>;
  turns: StoryTurn[];
};

/** A role that can be attached to a new Story. */
export type StoryRoleChoice = {
  id: string;
  name: string;
  description: string;
  avatarUrl?: string;
};

/** Input accepted by stories.create. */
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

/** Stable error exposed by the Story bridge client. */
export class StoryBridgeError extends Error {
  constructor(
    message: string,
    readonly code: string,
  ) {
    super(message);
    this.name = "StoryBridgeError";
  }
}
