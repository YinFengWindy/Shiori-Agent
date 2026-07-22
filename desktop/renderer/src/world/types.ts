/** A world shown in the workspace switcher. */
export type WorldSummary = {
  id: string;
  name: string;
  premise: string;
  currentTimeLabel: string;
  activeOcId: string | null;
  status: WorldRunStatus;
};

/** Player-facing lifecycle state for a world run. */
export type WorldRunStatus = "idle" | "running" | "action_required" | "barrier" | "stopped" | "resumable";

/** A player-created character living on the shared world timeline. */
export type WorldOc = {
  id: string;
  name: string;
  identity: string;
  location: string;
  avatarUrl?: string;
  primaryGoal: string;
  constraints: string[];
  autonomy: "manual" | "guided" | "autonomous";
  isActive: boolean;
};

/** A participant presented in the current scene. */
export type SceneParticipant = {
  id: string;
  name: string;
  role: "speaker" | "actor" | "observer" | "controlled_oc";
  avatarUrl?: string;
};

/** One committed, player-visible narrative beat. */
export type SceneBeat = {
  id: string;
  order: number;
  timeLabel: string;
  speakerName?: string;
  kind: "dialogue" | "action" | "environment";
  content: string;
  shot?: SceneShot;
  isCritical?: boolean;
};

/** One visual shot and all retained presentation alternatives. */
export type SceneShot = {
  id: string;
  prompt: string;
  status: "developing" | "ready" | "failed";
  activeAssetId?: string;
  assets: SceneShotAsset[];
};

/** A retained rendering of a scene shot. */
export type SceneShotAsset = {
  id: string;
  imageUrl: string;
  createdAtLabel: string;
};

/** A player choice that blocks all world progression at a shared instant. */
export type DecisionBarrier = {
  id: string;
  title: string;
  context: string;
  affectedOcNames: string[];
  choices: Array<{ id: string; label: string; consequence?: string }>;
};

/** Current scene read model. */
export type WorldScene = {
  title: string;
  location: string;
  timeLabel: string;
  participants: SceneParticipant[];
  beats: SceneBeat[];
  actionPrompt: string;
  opportunities: string[];
  barriers: DecisionBarrier[];
};

/** Complete renderer read model for a world. */
export type WorldDetails = WorldSummary & {
  ocs: WorldOc[];
  scene: WorldScene;
  relatedCharacters: Array<{ id: string; name: string; relationship: string; avatarUrl?: string }>;
  performance: { active: boolean; label: string; canCancel: boolean };
};

/** A role template that can be adapted as a native identity. */
export type WorldRoleChoice = {
  id: string;
  name: string;
  description: string;
  avatarUrl?: string;
};

/** Semantic world and first-OC input used to generate a reviewable draft. */
export type WorldCreationInput = {
  name: string;
  premise: string;
  rules: string;
  tone: string;
  selectedRoleIds: string[];
  seed: string;
  firstOc: {
    name: string;
    identity: string;
    entryTime: string;
    entryLocation: string;
    primaryGoal: string;
  };
};

/** Editable native-identity proposal returned before world creation. */
export type NativeIdentityDraft = {
  roleId: string;
  roleName: string;
  nativeName: string;
  identity: string;
  history: string;
  relationships: string;
  accepted: boolean;
};

/** Reviewable result of world generation. */
export type WorldCreationDraft = {
  id: string;
  input: WorldCreationInput;
  nativeIdentities: NativeIdentityDraft[];
};

/** An immutable world-history entry. */
export type WorldTimelineEntry = {
  id: string;
  timeLabel: string;
  title: string;
  summary: string;
  visibility: "known" | "omniscient";
  involvedNames: string[];
  canCopy: boolean;
  canEnter: boolean;
};

/** Historical-entry proposal and its causal impact. */
export type BackfillPreview = {
  anchorId: string;
  oc: WorldCreationInput["firstOc"];
  stages: Array<{ title: string; summary: string; playable: boolean }>;
  conflicts: string[];
  allowed: boolean;
};

/** Event payload used to append committed content after catch-up. */
export type WorldCatchUp = {
  cursor: string;
  beats: SceneBeat[];
  world?: WorldDetails;
};

/** Stable error exposed by the renderer bridge client. */
export class WorldBridgeError extends Error {
  constructor(
    message: string,
    readonly code: string,
  ) {
    super(message);
    this.name = "WorldBridgeError";
  }
}
