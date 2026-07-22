/// <reference types="node" />
import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { canSubmitWorldAction, mergeCommittedBeats, selectActiveOc, selectTimelineEntries } from "./selectors";
import { createSceneBeat, createWorldDetails } from "./testFixtures";

describe("world selectors", () => {
  it("blocks every action while a shared decision barrier exists", () => {
    const world = createWorldDetails({ scene: { ...createWorldDetails().scene, barriers: [{ id: "barrier", title: "警钟", context: "两位 OC 同时听见钟声", affectedOcNames: ["岚"], choices: [] }] } });
    assert.equal(canSubmitWorldAction(world), false);
  });

  it("merges replayed committed beats without duplicates and restores narrative order", () => {
    const first = createSceneBeat({ id: "first", order: 1 });
    const second = createSceneBeat({ id: "second", order: 2 });
    const merged = mergeCommittedBeats([second], [first, second]);
    assert.deepEqual(merged.map((beat) => beat.id), ["first", "second"]);
  });

  it("selects the controlled OC and filters private history in cognitive view", () => {
    assert.equal(selectActiveOc(createWorldDetails())?.name, "岚");
    const entries = [
      { id: "known", timeLabel: "清晨", title: "抵达", summary: "看见港口", visibility: "known" as const, involvedNames: [], canCopy: true, canEnter: true },
      { id: "hidden", timeLabel: "清晨", title: "密谈", summary: "未被看见", visibility: "omniscient" as const, involvedNames: [], canCopy: true, canEnter: false },
    ];
    assert.deepEqual(selectTimelineEntries(entries, "known").map((entry) => entry.id), ["known"]);
  });
});
