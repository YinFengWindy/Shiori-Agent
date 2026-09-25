import assert from "node:assert/strict";
import { afterEach, describe, it } from "node:test";
import { act, type ReactElement } from "react";
import { appearancePrefsStorageKey } from "../appearancePrefs";
import { MascotOnStage } from "../mascot/MascotOnStage";
import { inlineErrorLines } from "../mascot/mascotLines";
import { mountTestComponent } from "../testing/domTestHarness";
import { resetAppearancePrefsCache } from "../useAppearancePrefs";
import { InlineError } from "./InlineError";

afterEach(() => resetAppearancePrefsCache());

/** Mounts `element` with 设置 › 外观 › 看板娘 set to `mascot`. */
async function mount(element: ReactElement, mascot = true) {
  const view = await mountTestComponent(null);
  resetAppearancePrefsCache();
  window.localStorage.setItem(appearancePrefsStorageKey, JSON.stringify({ version: 1, backdropMotion: true, mascot }));
  await view.render(element);
  return view;
}

const block = (container: HTMLElement) => container.querySelector('[role="alert"], [role="status"]');

describe("InlineError", () => {
  it("lets 吟风 lead with her face and line, then the original message, the cause behind 详情", async () => {
    const view = await mount(<InlineError persona="settingsSaveFailed" message="保存失败：磁盘已满" detail="OSError 28" />);
    try {
      const root = block(view.container);
      assert.equal(root?.getAttribute("role"), "alert");
      assert.equal(root?.getAttribute("data-persona"), "settingsSaveFailed");
      assert.equal(root?.querySelector('[data-testid="mascot-face"]')?.getAttribute("data-expression"), inlineErrorLines.settingsSaveFailed.expression);
      const text = root?.textContent ?? "";
      assert.ok(text.indexOf(inlineErrorLines.settingsSaveFailed.text) === 0, text);
      assert.ok(text.indexOf("保存失败：磁盘已满") > 0, text);
      assert.doesNotMatch(text, /OSError/);
      const toggle = Array.from(root?.querySelectorAll("button") ?? []).find((button) => button.textContent?.includes("详情"));
      await act(async () => toggle?.click());
      assert.match(root?.textContent ?? "", /OSError 28/);
    } finally { await view.cleanup(); }
  });

  it("defaults to her generic line", async () => {
    const view = await mount(<InlineError message="出错了" />);
    try {
      assert.equal(block(view.container)?.getAttribute("data-persona"), "generic");
      assert.match(block(view.container)?.textContent ?? "", new RegExp(inlineErrorLines.generic.text));
    } finally { await view.cleanup(); }
  });

  it("is the plain block with the 看板娘 off, with persona false, and where she already stands", async () => {
    const cases: Array<[string, ReactElement, boolean]> = [
      ["看板娘 off", <InlineError message="出错了" />, false],
      ["persona false", <InlineError persona={false} message="出错了" />, true],
      ["on stage", <MascotOnStage><InlineError message="出错了" /></MascotOnStage>, true],
    ];
    for (const [label, element, mascot] of cases) {
      const view = await mount(element, mascot);
      try {
        const root = block(view.container);
        assert.equal(root?.querySelector('[data-testid="mascot-face"]'), null, label);
        assert.equal(root?.getAttribute("data-persona"), null, label);
        assert.equal(root?.textContent, "出错了", label);
        assert.ok(root?.querySelector("svg"), `${label}: the warning glyph stands in for her`);
      } finally { await view.cleanup(); }
    }
  });

  it("stays plain inside an inactive MascotOnStage, and nested stages keep her out", async () => {
    const view = await mount(<MascotOnStage active={false}><InlineError message="出错了" /></MascotOnStage>);
    try {
      assert.ok(block(view.container)?.querySelector('[data-testid="mascot-face"]'));
      await view.render(<MascotOnStage><MascotOnStage active={false}><InlineError message="出错了" /></MascotOnStage></MascotOnStage>);
      assert.equal(block(view.container)?.querySelector('[data-testid="mascot-face"]'), null);
    } finally { await view.cleanup(); }
  });

  it("draws a card with a title, her speech bubble, actions and a close button", async () => {
    let dismissed = 0;
    const view = await mount(<InlineError layout="card" title="生成失败" message="timeout" actions={<button type="button">知道了</button>} onDismiss={() => { dismissed += 1; }} />);
    try {
      const root = block(view.container);
      assert.equal(root?.querySelector('[data-testid="mascot-face"]')?.getAttribute("data-size"), "lg");
      assert.match(root?.querySelector('[data-testid="mascot-line"]')?.textContent ?? "", /吟风/);
      assert.match(root?.textContent ?? "", /生成失败/);
      assert.ok(Array.from(root?.querySelectorAll("button") ?? []).some((button) => button.textContent === "知道了"));
      await act(async () => root?.querySelector<HTMLButtonElement>('[aria-label="关闭"]')?.click());
      assert.equal(dismissed, 1);
    } finally { await view.cleanup(); }
  });

  it("announces a requested result politely with role status", async () => {
    const view = await mount(<InlineError role="status" persona="connectionTestFailed" message="401" />);
    try {
      assert.equal(block(view.container)?.getAttribute("role"), "status");
    } finally { await view.cleanup(); }
  });
});
