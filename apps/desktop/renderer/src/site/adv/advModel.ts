/**
 * Pure ADV (galgame dialogue) state machine for the site's 「开始」 screen.
 *
 * No React, no timers: time only moves through explicit `tick` actions, so
 * the typewriter, auto mode and every transition are deterministic and unit
 * testable. `useAdvDialogue` drives it with requestAnimationFrame.
 *
 * Flow: opening lines → choice list → a topic's lines → back to the choice
 * list (topic marked visited) → … → the exit choice plays the closing lines
 * → phase "ended" (the screen returns to the title).
 */

import { advanceTypewriter, startTypewriter } from "../../shared/adv/typewriter";

/**
 * What fills the stage above the dialogue box while a segment plays: 吟风's
 * standing sprite, or an event CG that takes the sprite's place. `key` names
 * an art slot; the screen maps slots to images.
 */
export interface AdvArt<Key extends string = string> {
  readonly kind: "sprite" | "cg";
  readonly key: Key;
}

/** A run of lines spoken in one go, with the art shown while it plays. */
export interface AdvSegment<Art extends AdvArt = AdvArt> {
  readonly art: Art;
  readonly lines: readonly string[];
}

/** One selectable topic in the choice list. */
export interface AdvTopic<Art extends AdvArt = AdvArt> extends AdvSegment<Art> {
  readonly id: string;
  readonly label: string;
}

/** The whole dialogue: opening, the topics offered as choices, and the exit. `Art` narrows the art each segment names. */
export interface AdvScript<Art extends AdvArt = AdvArt> {
  readonly speaker: string;
  readonly opening: AdvSegment<Art>;
  /** Text shown in the dialogue box while the choice list is up. */
  readonly choicePrompt: { readonly first: string; readonly again: string };
  readonly topics: readonly AdvTopic<Art>[];
  /** The last choice (“没什么想问的了”): its lines close the dialogue. */
  readonly exit: AdvSegment<Art> & { readonly label: string };
}

/** Timing inputs; may change between actions (text speed is live). */
export interface AdvConfig<Art extends AdvArt = AdvArt> {
  readonly script: AdvScript<Art>;
  /** Typewriter speed; 0 shows each line in full immediately. */
  readonly msPerChar: number;
  /** prefers-reduced-motion: every line is shown in full at once. */
  readonly reducedMotion: boolean;
}

export type AdvSegmentRef = { readonly kind: "opening" } | { readonly kind: "topic"; readonly topicId: string } | { readonly kind: "closing" };

/** Backlog history: every line started so far, plus which choices were picked. */
export type AdvBacklogEntry = { readonly kind: "line"; readonly text: string } | { readonly kind: "choice"; readonly label: string };

export interface AdvState {
  readonly phase: "line" | "choice" | "ended";
  readonly segment: AdvSegmentRef;
  readonly lineIndex: number;
  /** Characters of the current line revealed so far. */
  readonly shownChars: number;
  /** Elapsed typewriter time not yet converted into a whole character. */
  readonly pendingMs: number;
  readonly autoMode: boolean;
  /** Time spent on a completed line while auto mode is on. */
  readonly autoElapsedMs: number;
  readonly visited: readonly string[];
  readonly backlog: readonly AdvBacklogEntry[];
}

export type AdvAction =
  | { readonly type: "tick"; readonly elapsedMs: number }
  | { readonly type: "click" }
  | { readonly type: "skip" }
  | { readonly type: "toggleAuto" }
  | { readonly type: "choose"; readonly choiceId: string };

/** Choice id of the script's exit option (“没什么想问的了”). */
export const ADV_EXIT_CHOICE_ID = "exit";

/** How long auto mode lingers on a completed line: longer lines wait longer. */
export function autoAdvanceDelayMs(text: string): number {
  return 1200 + text.length * 60;
}

function topicOf<Art extends AdvArt>(script: AdvScript<Art>, topicId: string): AdvTopic<Art> {
  const topic = script.topics.find((candidate) => candidate.id === topicId);
  if (!topic) throw new Error(`Unknown ADV topic: ${topicId}`);
  return topic;
}

function segmentOf<Art extends AdvArt>(ref: AdvSegmentRef, script: AdvScript<Art>): AdvSegment<Art> {
  if (ref.kind === "opening") return script.opening;
  if (ref.kind === "closing") return script.exit;
  return topicOf(script, ref.topicId);
}

/** Enter `lineIndex` of `segment`: reset typewriter/auto timers, log the line. */
function startLine(state: AdvState, segment: AdvSegmentRef, lineIndex: number, config: AdvConfig): AdvState {
  const text = segmentOf(segment, config.script).lines[lineIndex];
  return {
    ...state,
    phase: "line",
    segment,
    lineIndex,
    ...startTypewriter(text.length, config),
    autoElapsedMs: 0,
    backlog: [...state.backlog, { kind: "line", text }],
  };
}

/** Leave the current segment: closing ends the dialogue, anything else offers choices. */
function finishSegment(state: AdvState): AdvState {
  return { ...state, phase: state.segment.kind === "closing" ? "ended" : "choice", pendingMs: 0, autoElapsedMs: 0 };
}

export function createAdvState(config: AdvConfig): AdvState {
  const empty: AdvState = {
    phase: "line",
    segment: { kind: "opening" },
    lineIndex: 0,
    shownChars: 0,
    pendingMs: 0,
    autoMode: false,
    autoElapsedMs: 0,
    visited: [],
    backlog: [],
  };
  return startLine(empty, { kind: "opening" }, 0, config);
}

/** The line currently in the dialogue box, or null outside the "line" phase. */
export function currentLine(state: AdvState, script: AdvScript): string | null {
  if (state.phase !== "line") return null;
  return segmentOf(state.segment, script).lines[state.lineIndex];
}

export function isLineComplete(state: AdvState, script: AdvScript): boolean {
  const line = currentLine(state, script);
  return line !== null && state.shownChars >= line.length;
}

/** The topic being explained right now (for the chapter caption), else null. */
export function currentTopic<Art extends AdvArt>(state: AdvState, script: AdvScript<Art>): AdvTopic<Art> | null {
  if (state.phase !== "line" || state.segment.kind !== "topic") return null;
  return topicOf(script, state.segment.topicId);
}

/**
 * Art to show: the segment's art while speaking (a topic's event CG, say),
 * the opening art while the choices are up — so a topic's CG gives way to
 * the sprite again when it ends — and the closing art once it has ended.
 */
export function currentArt<Art extends AdvArt>(state: AdvState, script: AdvScript<Art>): Art {
  if (state.phase === "line") return segmentOf(state.segment, script).art;
  return state.phase === "ended" ? script.exit.art : script.opening.art;
}

/** The choice list (topics in script order, then the exit) with 已读 flags. */
export function advChoices(state: AdvState, script: AdvScript) {
  return [
    ...script.topics.map((topic) => ({ id: topic.id, label: topic.label, visited: state.visited.includes(topic.id) })),
    { id: ADV_EXIT_CHOICE_ID, label: script.exit.label, visited: false },
  ];
}

export function choicePrompt(state: AdvState, script: AdvScript): string {
  return state.visited.length ? script.choicePrompt.again : script.choicePrompt.first;
}

function advance(state: AdvState, config: AdvConfig): AdvState {
  const segment = segmentOf(state.segment, config.script);
  if (state.lineIndex + 1 < segment.lines.length) return startLine(state, state.segment, state.lineIndex + 1, config);
  return finishSegment(state);
}

function tick(state: AdvState, elapsedMs: number, config: AdvConfig): AdvState {
  const line = currentLine(state, config.script);
  if (line === null || elapsedMs <= 0) return state;
  if (state.shownChars < line.length) return { ...state, ...advanceTypewriter(state, elapsedMs, line.length, config) };
  if (!state.autoMode) return state;
  const autoElapsedMs = state.autoElapsedMs + elapsedMs;
  return autoElapsedMs >= autoAdvanceDelayMs(line) ? advance(state, config) : { ...state, autoElapsedMs };
}

/** Log every line of the current segment not yet started, so the backlog stays whole after a skip. */
function logRemainingLines(state: AdvState, config: AdvConfig): AdvState {
  const rest = segmentOf(state.segment, config.script).lines.slice(state.lineIndex + 1);
  return { ...state, backlog: [...state.backlog, ...rest.map((text) => ({ kind: "line" as const, text }))] };
}

function choose(state: AdvState, choiceId: string, config: AdvConfig): AdvState {
  const { script } = config;
  if (choiceId === ADV_EXIT_CHOICE_ID) {
    const picked: AdvState = { ...state, backlog: [...state.backlog, { kind: "choice", label: script.exit.label }] };
    return startLine(picked, { kind: "closing" }, 0, config);
  }
  const topic = topicOf(script, choiceId);
  const picked: AdvState = {
    ...state,
    visited: state.visited.includes(topic.id) ? state.visited : [...state.visited, topic.id],
    backlog: [...state.backlog, { kind: "choice", label: topic.label }],
  };
  return startLine(picked, { kind: "topic", topicId: topic.id }, 0, config);
}

/**
 * Apply one action. Unchanged state is returned as-is (same reference) so
 * React subscribers skip no-op renders.
 */
export function advReducer(state: AdvState, action: AdvAction, config: AdvConfig): AdvState {
  switch (action.type) {
    case "tick":
      return tick(state, action.elapsedMs, config);
    case "toggleAuto":
      return state.phase === "ended" ? state : { ...state, autoMode: !state.autoMode, autoElapsedMs: 0 };
    case "click": {
      const line = currentLine(state, config.script);
      if (line === null) return state;
      // First click completes a typing line; the next one advances.
      if (state.shownChars < line.length) return { ...state, shownChars: line.length, pendingMs: 0 };
      return advance(state, config);
    }
    case "skip":
      return state.phase === "line" ? finishSegment(logRemainingLines(state, config)) : state;
    case "choose":
      return state.phase === "choice" ? choose(state, action.choiceId, config) : state;
  }
}
