/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import * as lines from "./mascotLines";
import { aboutIdleLines, pickMascotLine, startupGreetingLines, startupTimeBandAt, type MascotLine } from "./mascotLines";
import { mascotExpressions } from "./mascotExpressions";

const at = (hours: number, minutes = 0) => new Date(2026, 8, 25, hours, minutes, 0, 0);

/** Every line in the module, however it is grouped. */
function allLines(): MascotLine[] {
  const found: MascotLine[] = [];
  const visit = (value: unknown) => {
    if (!value || typeof value !== "object") return;
    if ("text" in value && "expression" in value) {
      found.push(value as MascotLine);
      return;
    }
    Object.values(value).forEach(visit);
  };
  Object.values(lines).forEach(visit);
  return found;
}

describe("pickMascotLine", () => {
  it("never repeats the previous line when the pool offers another", () => {
    let previous: MascotLine | null = null;
    // Any random value, including the extremes, must avoid the last line.
    for (const roll of [0, 0.2, 0.5, 0.8, 0.999999, 0, 0.999999]) {
      const next = pickMascotLine(aboutIdleLines, previous, () => roll);
      assert.notEqual(next, previous);
      assert.ok(aboutIdleLines.includes(next));
      previous = next;
    }
  });

  it("keeps the only line of a one-line pool, and ignores a previous line from another pool", () => {
    const [only] = startupGreetingLines.dusk;
    assert.equal(pickMascotLine(startupGreetingLines.dusk, only), only);
    assert.equal(pickMascotLine(aboutIdleLines, only, () => 0), aboutIdleLines[0]);
  });
});

describe("startupTimeBandAt", () => {
  it("switches at each band boundary in local time", () => {
    assert.equal(startupTimeBandAt(at(4, 59)), "lateNight");
    assert.equal(startupTimeBandAt(at(5)), "morning");
    assert.equal(startupTimeBandAt(at(9, 59)), "morning");
    assert.equal(startupTimeBandAt(at(10)), "day");
    assert.equal(startupTimeBandAt(at(16, 59)), "day");
    assert.equal(startupTimeBandAt(at(17)), "dusk");
    assert.equal(startupTimeBandAt(at(19, 59)), "dusk");
    assert.equal(startupTimeBandAt(at(20)), "evening");
    assert.equal(startupTimeBandAt(at(23, 59)), "evening");
    assert.equal(startupTimeBandAt(at(0)), "lateNight");
  });

  it("greets each band with its own lines", () => {
    assert.match(pickMascotLine(startupGreetingLines[startupTimeBandAt(at(7))], null, () => 0).text, /早/);
    assert.match(pickMascotLine(startupGreetingLines[startupTimeBandAt(at(2))], null, () => 0).text, /睡/);
  });
});

describe("mascot lines", () => {
  it("stay within 40 characters and use one of her eight expressions", () => {
    const found = allLines();
    assert.ok(found.length >= 18, `found ${found.length}`);
    for (const line of found) {
      assert.ok([...line.text].length <= 40, line.text);
      assert.ok(mascotExpressions.includes(line.expression), line.text);
    }
  });
});
