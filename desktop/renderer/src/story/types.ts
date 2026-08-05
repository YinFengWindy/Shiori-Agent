import type { StoryTimeBand } from "./storyTime";

/** A Story entry shown in the launcher. */
export type StorySummary = {
  storyId: string;
  relativeDbPath: string;
  title: string;
  status: "active" | "archived" | "deleting";
  createdAt: string;
  currentTimeBand: StoryTimeBand;
};

/** Story operation state owned by the current segment. */
export type StoryOperation = "idle" | "awaiting_player" | "generating";

/** Lifecycle state of a Story-owned image resource. */
export type StoryResourceStatus = "generating" | "ready" | "failed";
export type StoryVisualType = "scene" | "character";

/** One image owned by a Story and shown by its CG collection. */
export type StoryResource = {
  id: string;
  storyId: string;
  kind: "background" | "cg";
  visualType: StoryVisualType;
  status: StoryResourceStatus;
  path: string | null;
  prompt: string;
  sourceTurnId: string | null;
  sequence: number;
  errorCode: string | null;
  createdAt: string;
  updatedAt: string;
};

/** Story grouping returned by the main-menu CG collection. */
export type StoryCgGallery = {
  storyId: string;
  title: string;
  status: "active" | "archived" | "deleting";
  createdAt: string;
  items: StoryResource[];
};

/** Persisted Story segment read model. */
export type StorySegment = {
  id: string;
  sequence: number;
  storyDate: string;
  timeBand: StoryTimeBand;
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
  storyDate: string;
  timeBand: StoryTimeBand;
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
    illustrations?: string[];
    runtime_config?: Record<string, unknown>;
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
  backgroundResource: StoryResource | null;
  cgGallery: StoryResource[];
  currentStoryDate: string;
  currentTimeBand: StoryTimeBand;
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
  storyDate: string;
  timeBand: StoryTimeBand | "";
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
