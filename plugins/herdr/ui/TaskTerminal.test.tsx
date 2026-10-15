import assert from "node:assert/strict";
import { test } from "node:test";
import { act } from "react";
import { mountTestComponent } from "@yinfengwindy/shiori-sdk/testing";
import { TaskTerminal } from "./TaskTerminal";

/** happy-dom has no layout: give the terminal a 100px viewport over content 10px per character line. */
function layout(element: HTMLElement) {
  Object.defineProperty(element, "clientHeight", { configurable: true, get: () => 100 });
  Object.defineProperty(element, "scrollHeight", { configurable: true, get: () => (element.textContent ?? "").split("\n").length * 10 });
}

const lines = (count: number, from = 1) => Array.from({ length: count }, (_, index) => `line ${from + index}`).join("\n");

async function scrollTo(element: HTMLElement, top: number) {
  element.scrollTop = top;
  await act(async () => { element.dispatchEvent(new Event("scroll")); });
}

test("follows new output at the bottom; scrolled up it holds the text and offers the new output", async () => {
  const view = await mountTestComponent(<TaskTerminal output={lines(20)} />);
  try {
    const terminal = view.container.querySelector("pre");
    assert.ok(terminal);
    layout(terminal);
    await view.render(<TaskTerminal output={lines(30)} />);
    assert.equal(terminal.scrollTop, 300, "at the bottom it follows");
    assert.equal(view.container.querySelector("button"), null);

    await scrollTo(terminal, 50);
    await view.render(<TaskTerminal output={lines(30, 11)} />);
    assert.equal(terminal.textContent, lines(30), "the text being read does not move");
    assert.equal(terminal.scrollTop, 50);
    const jump = view.container.querySelector("button");
    assert.equal(jump?.textContent, "有新输出");

    await act(async () => jump?.click());
    assert.equal(terminal.textContent, lines(30, 11));
    assert.equal(terminal.scrollTop, 300);
    assert.equal(view.container.querySelector("button"), null);
  } finally { await view.cleanup(); }
});

test("scrolled up without new output there is no entry, and reaching the bottom follows again", async () => {
  const view = await mountTestComponent(<TaskTerminal output={lines(30)} />);
  try {
    const terminal = view.container.querySelector("pre");
    assert.ok(terminal);
    layout(terminal);
    await scrollTo(terminal, 0);
    assert.equal(view.container.querySelector("button"), null);
    await scrollTo(terminal, 200);
    await view.render(<TaskTerminal output={lines(40)} />);
    assert.equal(terminal.scrollTop, 400);
  } finally { await view.cleanup(); }
});

test("a resize while following keeps the end in view; scrolled up it leaves the position alone", async () => {
  const resized: Array<() => void> = [];
  class ManualResizeObserver {
    constructor(callback: () => void) { resized.push(callback); }
    observe() {}
    disconnect() {}
  }
  const view = await mountTestComponent(<TaskTerminal output={lines(30)} />, { windowGlobals: { ResizeObserver: ManualResizeObserver } });
  try {
    const terminal = view.container.querySelector("pre");
    assert.ok(terminal);
    layout(terminal);
    terminal.scrollTop = 200;
    act(() => resized.forEach((callback) => callback()));
    assert.equal(terminal.scrollTop, 300);
    await scrollTo(terminal, 50);
    act(() => resized.forEach((callback) => callback()));
    assert.equal(terminal.scrollTop, 50);
  } finally { await view.cleanup(); }
});
