import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  canAdvanceDialogue,
  currentDialogueLine,
  emptyOnboardingDialogue,
  isDialogueLineComplete,
  isLastDialogueLine,
  onboardingDialogueReducer as reduce,
} from "./onboardingDialogue";

const timing = { msPerChar: 10, reducedMotion: false };
const lines = [{ expression: "smug" as const, text: "你好" }, { expression: "neutral" as const, text: "再见" }];

describe("onboarding dialogue", () => {
  it("types a line, completes it on click, then advances and waits on the last line", () => {
    let state = reduce(emptyOnboardingDialogue, { type: "say", scene: "model", lines }, timing);
    assert.equal(currentDialogueLine(state)?.text, "你好");
    assert.equal(state.progress.shownChars, 0);
    state = reduce(state, { type: "tick", elapsedMs: 10 }, timing);
    assert.equal(state.progress.shownChars, 1);
    state = reduce(state, { type: "click" }, timing);
    assert.ok(isDialogueLineComplete(state));
    const serial = state.serial;
    state = reduce(state, { type: "click" }, timing);
    assert.equal(currentDialogueLine(state)?.text, "再见");
    assert.equal(state.serial, serial + 1);
    assert.ok(isLastDialogueLine(state));
    state = reduce(state, { type: "click" }, timing);
    assert.equal(canAdvanceDialogue(state), false);
    assert.equal(reduce(state, { type: "click" }, timing), state);
  });

  it("replaces whatever is showing when a reaction is said", () => {
    const intro = reduce(emptyOnboardingDialogue, { type: "say", scene: "role", lines }, timing);
    const reaction = reduce(intro, { type: "say", scene: "role", lines: [{ expression: "surprised", text: "哇" }] }, timing);
    assert.equal(currentDialogueLine(reaction)?.expression, "surprised");
    assert.ok(isLastDialogueLine(reaction));
    assert.ok(reaction.serial > intro.serial);
  });

  it("shows whole lines at once under reduced motion", () => {
    const state = reduce(emptyOnboardingDialogue, { type: "say", scene: "model", lines }, { msPerChar: 10, reducedMotion: true });
    assert.ok(isDialogueLineComplete(state));
  });

  it("ignores clicks and ticks before anything is said", () => {
    assert.equal(reduce(emptyOnboardingDialogue, { type: "click" }, timing), emptyOnboardingDialogue);
    assert.equal(reduce(emptyOnboardingDialogue, { type: "tick", elapsedMs: 50 }, timing), emptyOnboardingDialogue);
  });
});
