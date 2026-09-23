/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  ADV_EXIT_CHOICE_ID,
  advChoices,
  advReducer,
  autoAdvanceDelayMs,
  choicePrompt,
  createAdvState,
  currentArt,
  currentLine,
  currentTopic,
  isLineComplete,
  type AdvAction,
  type AdvConfig,
  type AdvScript,
  type AdvState,
} from "./advModel";

const SCRIPT: AdvScript = {
  speaker: "吟风",
  opening: { art: "open", lines: ["你好呀", "我是吟风"] },
  choicePrompt: { first: "选吧", again: "还想听？" },
  topics: [
    { id: "chat", label: "聊天", art: "chat-art", lines: ["聊天一", "聊天二", "聊天三"] },
    { id: "pet", label: "桌宠", art: "pet-art", lines: ["桌宠一"] },
  ],
  exit: { label: "没什么想问的了", art: "bye-art", lines: ["再见"] },
};

const CONFIG: AdvConfig = { script: SCRIPT, msPerChar: 50, reducedMotion: false };

function run(state: AdvState, actions: AdvAction[], config: AdvConfig = CONFIG): AdvState {
  return actions.reduce((current, action) => advReducer(current, action, config), state);
}

const click: AdvAction = { type: "click" };
/** Two clicks: complete the typing line, then advance past it. */
const next: AdvAction[] = [click, click];

function atChoices(): AdvState {
  return run(createAdvState(CONFIG), [...next, ...next]);
}

describe("typewriter", () => {
  it("starts on the first opening line with nothing revealed", () => {
    const state = createAdvState(CONFIG);
    assert.equal(state.phase, "line");
    assert.equal(currentLine(state, SCRIPT), "你好呀");
    assert.equal(state.shownChars, 0);
    assert.equal(currentArt(state, SCRIPT), "open");
  });

  it("reveals one character per msPerChar of ticked time, carrying remainders", () => {
    let state = createAdvState(CONFIG);
    state = run(state, [{ type: "tick", elapsedMs: 30 }]);
    assert.equal(state.shownChars, 0);
    state = run(state, [{ type: "tick", elapsedMs: 30 }]);
    assert.equal(state.shownChars, 1);
    state = run(state, [{ type: "tick", elapsedMs: 90 }]);
    assert.equal(state.shownChars, 3);
    assert.ok(isLineComplete(state, SCRIPT));
    // Further time never overshoots the line.
    state = run(state, [{ type: "tick", elapsedMs: 1000 }]);
    assert.equal(state.shownChars, 3);
  });

  it("picks up a new text speed on the next tick", () => {
    const state = run(createAdvState(CONFIG), [{ type: "tick", elapsedMs: 20 }], { ...CONFIG, msPerChar: 10 });
    assert.equal(state.shownChars, 2);
  });

  it("shows whole lines immediately under reduced motion", () => {
    const reduced: AdvConfig = { ...CONFIG, reducedMotion: true };
    let state = createAdvState(reduced);
    assert.ok(isLineComplete(state, SCRIPT));
    state = run(state, [click], reduced);
    assert.equal(currentLine(state, SCRIPT), "我是吟风");
    assert.ok(isLineComplete(state, SCRIPT));
  });
});

describe("click", () => {
  it("completes a typing line first, then advances", () => {
    let state = run(createAdvState(CONFIG), [click]);
    assert.equal(currentLine(state, SCRIPT), "你好呀");
    assert.ok(isLineComplete(state, SCRIPT));
    state = run(state, [click]);
    assert.equal(currentLine(state, SCRIPT), "我是吟风");
    assert.equal(state.shownChars, 0);
  });

  it("shows the choice list after the opening's last line", () => {
    const state = atChoices();
    assert.equal(state.phase, "choice");
    assert.equal(currentLine(state, SCRIPT), null);
    assert.equal(choicePrompt(state, SCRIPT), "选吧");
    assert.deepEqual(
      advChoices(state, SCRIPT).map((choice) => choice.label),
      ["聊天", "桌宠", "没什么想问的了"],
    );
    // Clicking does nothing while choices are up.
    assert.equal(run(state, [click]), state);
  });
});

describe("skip", () => {
  it("jumps from mid-opening straight to the choice list", () => {
    const state = run(createAdvState(CONFIG), [{ type: "skip" }]);
    assert.equal(state.phase, "choice");
  });

  it("jumps from mid-topic back to the choice list", () => {
    const state = run(atChoices(), [{ type: "choose", choiceId: "chat" }, { type: "skip" }]);
    assert.equal(state.phase, "choice");
    assert.deepEqual(state.visited, ["chat"]);
  });

  it("ends the dialogue when skipping the closing lines", () => {
    const state = run(atChoices(), [{ type: "choose", choiceId: ADV_EXIT_CHOICE_ID }, { type: "skip" }]);
    assert.equal(state.phase, "ended");
  });

  it("still logs the skipped lines in the backlog", () => {
    const state = run(createAdvState(CONFIG), [{ type: "skip" }]);
    assert.deepEqual(state.backlog, [
      { kind: "line", text: "你好呀" },
      { kind: "line", text: "我是吟风" },
    ]);
  });
});

describe("auto mode", () => {
  it("advances a completed line after a length-scaled delay", () => {
    let state = run(createAdvState(CONFIG), [{ type: "toggleAuto" }, click]);
    assert.ok(state.autoMode);
    const delay = autoAdvanceDelayMs("你好呀");
    state = run(state, [{ type: "tick", elapsedMs: delay - 1 }]);
    assert.equal(currentLine(state, SCRIPT), "你好呀");
    state = run(state, [{ type: "tick", elapsedMs: 1 }]);
    assert.equal(currentLine(state, SCRIPT), "我是吟风");
  });

  it("waits longer on longer lines", () => {
    assert.ok(autoAdvanceDelayMs("一二三四五六七八九十") > autoAdvanceDelayMs("一二三"));
  });

  it("types the line out before the delay starts counting", () => {
    let state = run(createAdvState(CONFIG), [{ type: "toggleAuto" }]);
    // 3 chars × 50ms to type; the auto delay only starts after that.
    state = run(state, [{ type: "tick", elapsedMs: 150 }]);
    assert.ok(isLineComplete(state, SCRIPT));
    state = run(state, [{ type: "tick", elapsedMs: autoAdvanceDelayMs("你好呀") - 1 }]);
    assert.equal(currentLine(state, SCRIPT), "你好呀");
  });

  it("does not advance without auto mode, and never picks a choice by itself", () => {
    const idle = run(createAdvState(CONFIG), [click, { type: "tick", elapsedMs: 60_000 }]);
    assert.equal(currentLine(idle, SCRIPT), "你好呀");
    const choosing = run(atChoices(), [{ type: "toggleAuto" }, { type: "tick", elapsedMs: 60_000 }]);
    assert.equal(choosing.phase, "choice");
  });

  it("toggles off again", () => {
    const state = run(createAdvState(CONFIG), [{ type: "toggleAuto" }, { type: "toggleAuto" }]);
    assert.equal(state.autoMode, false);
  });
});

describe("choices", () => {
  it("plays the chosen topic with its art, then returns to the choices", () => {
    let state = run(atChoices(), [{ type: "choose", choiceId: "chat" }]);
    assert.equal(currentLine(state, SCRIPT), "聊天一");
    assert.equal(currentArt(state, SCRIPT), "chat-art");
    assert.equal(currentTopic(state, SCRIPT)?.label, "聊天");
    state = run(state, [...next, ...next]);
    assert.equal(currentLine(state, SCRIPT), "聊天三");
    state = run(state, next);
    assert.equal(state.phase, "choice");
    assert.equal(currentArt(state, SCRIPT), "open");
    assert.equal(currentTopic(state, SCRIPT), null);
    assert.equal(choicePrompt(state, SCRIPT), "还想听？");
  });

  it("marks visited topics as 已读 and keeps them selectable", () => {
    let state = run(atChoices(), [{ type: "choose", choiceId: "pet" }, ...next]);
    assert.deepEqual(
      advChoices(state, SCRIPT).map((choice) => [choice.id, choice.visited]),
      [["chat", false], ["pet", true], [ADV_EXIT_CHOICE_ID, false]],
    );
    state = run(state, [{ type: "choose", choiceId: "pet" }, ...next]);
    assert.deepEqual(state.visited, ["pet"]);
  });

  it("ignores choose outside the choice phase and rejects unknown ids", () => {
    const opening = createAdvState(CONFIG);
    assert.equal(run(opening, [{ type: "choose", choiceId: "chat" }]), opening);
    assert.throws(() => run(atChoices(), [{ type: "choose", choiceId: "nope" }]));
  });

  it("the exit choice plays the closing line and then ends", () => {
    let state = run(atChoices(), [{ type: "choose", choiceId: ADV_EXIT_CHOICE_ID }]);
    assert.equal(currentLine(state, SCRIPT), "再见");
    assert.equal(currentArt(state, SCRIPT), "bye-art");
    state = run(state, next);
    assert.equal(state.phase, "ended");
    // Nothing moves after the end.
    assert.equal(run(state, [click, { type: "skip" }, { type: "toggleAuto" }]), state);
  });
});

describe("backlog", () => {
  it("records every line spoken so far and the picked choices, in order", () => {
    const state = run(atChoices(), [{ type: "choose", choiceId: "pet" }, ...next, { type: "choose", choiceId: ADV_EXIT_CHOICE_ID }]);
    assert.deepEqual(state.backlog, [
      { kind: "line", text: "你好呀" },
      { kind: "line", text: "我是吟风" },
      { kind: "choice", label: "桌宠" },
      { kind: "line", text: "桌宠一" },
      { kind: "choice", label: "没什么想问的了" },
      { kind: "line", text: "再见" },
    ]);
  });
});
