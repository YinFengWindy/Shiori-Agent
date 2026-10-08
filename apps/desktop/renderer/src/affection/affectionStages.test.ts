import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { it } from "node:test";
import { affectionMax, affectionMin, affectionStages, neutralAffectionStage } from "./affectionStages";

const backendAffection = new URL("../../../../backend/core/roles/relationship_runtime/affection.py", import.meta.url);

/** Every `AffectionStage("名", lower, upper)` of the backend module, in source order. */
function backendStages() {
  const source = readFileSync(backendAffection, "utf8");
  const declared = new Map(Array.from(
    source.matchAll(/^(\w+) = AffectionStage\("([^"]+)", (-?\d+), (-?\d+)\)/gm),
    ([, constant, name, lower, upper]) => [constant, { name, lower: Number(lower), upper: Number(upper) }],
  ));
  const tuple = /^AFFECTION_STAGES: [^=]+= \(\n([\s\S]*?)\n\)/m.exec(source.replaceAll("\r\n", "\n"));
  assert.ok(tuple, "AFFECTION_STAGES not found");
  return tuple[1].split("\n").map((line) => {
    const item = line.trim().replace(/,$/, "");
    const inline = /^AffectionStage\("([^"]+)", (-?\d+), (-?\d+)\)$/.exec(item);
    if (inline) return { name: inline[1], lower: Number(inline[2]), upper: Number(inline[3]) };
    const named = declared.get(item);
    assert.ok(named, `unrecognized stage entry: ${item}`);
    return named;
  });
}

it("matches the backend's AFFECTION_STAGES and covers -100–100 without gaps", () => {
  assert.deepEqual(affectionStages.map((stage) => ({ ...stage })), backendStages());
  assert.equal(affectionStages.find((stage) => stage.lower <= 0 && stage.upper >= 0)?.name, neutralAffectionStage);
  assert.equal(affectionStages[0].lower, affectionMin);
  assert.equal(affectionStages.at(-1)?.upper, affectionMax);
  affectionStages.slice(1).forEach((stage, index) => assert.equal(stage.lower, affectionStages[index].upper + 1));
});
