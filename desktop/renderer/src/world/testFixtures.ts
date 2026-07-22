import type { SceneBeat, WorldDetails, WorldSummary } from "./types";

/** Creates a compact committed beat for renderer tests. */
export function createSceneBeat(overrides: Partial<SceneBeat> = {}): SceneBeat {
  return {
    id: overrides.id ?? "beat-1",
    order: overrides.order ?? 1,
    timeLabel: overrides.timeLabel ?? "雨夜",
    speakerName: overrides.speakerName ?? "澪",
    kind: overrides.kind ?? "dialogue",
    content: overrides.content ?? "你终于来了。",
    shot: overrides.shot,
    isCritical: overrides.isCritical,
  };
}

/** Creates a complete world read model for renderer tests. */
export function createWorldDetails(overrides: Partial<WorldDetails> = {}): WorldDetails {
  return {
    id: overrides.id ?? "world-1",
    name: overrides.name ?? "雨港",
    premise: overrides.premise ?? "潮汐会带回被遗忘的名字。",
    currentTimeLabel: overrides.currentTimeLabel ?? "第三日 · 深夜",
    activeOcId: overrides.activeOcId ?? "oc-1",
    status: overrides.status ?? "action_required",
    ocs: overrides.ocs ?? [{ id: "oc-1", name: "岚", identity: "从北方来的抄写员", location: "旧港", primaryGoal: "找到失踪的姐姐", constraints: [], autonomy: "guided", isActive: true }],
    scene: overrides.scene ?? { title: "灯塔下", location: "旧港灯塔", timeLabel: "暴雨将至", participants: [{ id: "oc-1", name: "岚", role: "controlled_oc" }], beats: [createSceneBeat()], actionPrompt: "岚准备怎么做？", opportunities: ["灯塔门没有上锁"], barriers: [] },
    relatedCharacters: overrides.relatedCharacters ?? [{ id: "native-1", name: "澪", relationship: "刚刚相识" }],
    performance: overrides.performance ?? { active: true, label: "观看现场演出", canCancel: true },
  };
}

/** Creates the summary form of the world fixture. */
export function createWorldSummary(world = createWorldDetails()): WorldSummary {
  return { id: world.id, name: world.name, premise: world.premise, currentTimeLabel: world.currentTimeLabel, activeOcId: world.activeOcId, status: world.status };
}
