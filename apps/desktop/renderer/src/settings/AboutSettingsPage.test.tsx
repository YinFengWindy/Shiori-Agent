import assert from "node:assert/strict";
import test from "node:test";
import { act } from "react";
import type { DesktopUpdateApi, DesktopUpdateState } from "../../../src/updateContract.js";
import { appearancePrefsStorageKey } from "../shared/appearancePrefs";
import { mountTestComponent } from "../shared/testing/domTestHarness";
import { resetAppearancePrefsCache } from "../shared/useAppearancePrefs";
import { AboutSettingsPage } from "./AboutSettingsPage";

test("the visible update action checks, reports progress and installs only a ready update", async () => {
  const view = await mountTestComponent(null);
  let notify!: (state: DesktopUpdateState) => void;
  let checks = 0;
  let installs = 0;
  const opened: string[] = [];
  const snapshot: DesktopUpdateState = { revision: 0, currentVersion: "0.2.0", phase: "idle", latestVersion: null, progress: 0, error: null };
  const api: DesktopUpdateApi = {
    getState: async () => snapshot,
    check: async () => { checks += 1; return { ...snapshot, revision: 1, phase: "current" }; },
    install: async () => { installs += 1; },
    onState: (listener) => { notify = listener; return () => undefined; },
  };
  Object.defineProperty(window, "miraDesktop", { configurable: true, value: {
    updates: api,
    openExternal: async (url: string) => { opened.push(url); return { ok: true, error: null }; },
  } });
  try {
    await view.render(<AboutSettingsPage />);
    assert.match(view.container.textContent ?? "", /当前版本 v0.2.0/);
    const button = view.container.querySelector("button");
    assert.ok(button);
    await act(async () => button.click());
    assert.equal(checks, 1);
    assert.match(view.container.textContent ?? "", /已是最新版本/);
    await act(async () => notify({ ...snapshot, revision: 2, phase: "downloading", latestVersion: "0.3.0", progress: 45 }));
    assert.equal(button.disabled, true);
    assert.equal(view.container.querySelector("progress")?.value, 45);
    await act(async () => notify({ ...snapshot, revision: 3, phase: "downloaded", latestVersion: "0.3.0", progress: 100 }));
    assert.equal(button.textContent?.trim(), "重启并安装");
    assert.equal(button.disabled, false);
    await act(async () => button.click());
    assert.equal(installs, 1);
    for (const link of Array.from(view.container.querySelectorAll("a"))) await act(async () => link.click());
    assert.deepEqual(opened, [
      "https://github.com/YinFengWindy/Shiori-Agent/releases/latest",
      "https://github.com/YinFengWindy/Shiori-Agent",
      "mailto:3174898512@qq.com",
    ]);
  } finally { await view.cleanup(); }
});

test("renders no heading of its own, and its first content block carries no top margin", async () => {
  // The "关于" heading and its spacing are the shared SettingsSubsectionNav
  // header's job when this component is mounted through SettingsPage (issue
  // #230) — this component must neither render a competing heading nor
  // stack its own top margin on top of the header's, which briefly
  // regressed 「关于」 to more space under its title than every other
  // section (issue #230 review).
  const view = await mountTestComponent(null);
  Object.defineProperty(window, "miraDesktop", { configurable: true, value: {
    updates: {
      getState: async () => ({ revision: 0, currentVersion: "0.2.0", phase: "unsupported", latestVersion: null, progress: 0, error: null }),
      onState: () => () => undefined,
    },
  } });
  try {
    await view.render(<AboutSettingsPage />);
    assert.equal(view.container.querySelector("h2"), null);
    const root = view.container.querySelector('[data-testid="about-settings"]')!;
    const content = root.firstElementChild as HTMLElement;
    assert.ok(content, "expected AboutSettingsPage to render content");
    assert.equal(content.className.includes("mt-8"), false, "must not add its own top margin above the shared header's");
  } finally { await view.cleanup(); }
});

test("failed status loading remains retryable", async () => {
  const view = await mountTestComponent(null);
  const api: DesktopUpdateApi = {
    getState: async () => { throw new Error("connection lost"); },
    check: async () => ({ revision: 1, currentVersion: "0.2.0", phase: "current", latestVersion: null, progress: 0, error: null }),
    install: async () => undefined,
    onState: () => () => undefined,
  };
  Object.defineProperty(window, "miraDesktop", { configurable: true, value: { updates: api } });
  try {
    await view.render(<AboutSettingsPage />);
    assert.match(view.container.querySelector('[role="alert"]')?.textContent ?? "", /connection lost/);
    const button = view.container.querySelector("button");
    assert.ok(button);
    assert.equal(button.disabled, false);
    await act(async () => button.click());
    assert.equal(view.container.querySelector('[role="alert"]'), null);
    assert.match(view.container.textContent ?? "", /已是最新版本/);
  } finally { await view.cleanup(); }
});

test("puts 吟风 beside the version card with the 看板娘 on, and leaves the page plain with it off", async () => {
  resetAppearancePrefsCache();
  const view = await mountTestComponent(null);
  const api: DesktopUpdateApi = {
    getState: async () => ({ revision: 0, currentVersion: "0.2.0", phase: "idle", latestVersion: null, progress: 0, error: null }),
    check: async () => ({ revision: 1, currentVersion: "0.2.0", phase: "current", latestVersion: null, progress: 0, error: null }),
    install: async () => undefined,
    onState: () => () => undefined,
  };
  Object.defineProperty(window, "miraDesktop", { configurable: true, value: { updates: api } });
  try {
    await view.render(<AboutSettingsPage />);
    const mascot = view.container.querySelector('[data-testid="about-mascot"]');
    assert.ok(mascot?.querySelector('[aria-label="应用更新"]'), "the version card sits inside her layout");
    // A check she sees finish gets her 「已是最新」 line.
    await act(async () => view.container.querySelector<HTMLButtonElement>("button")?.click());
    assert.match(mascot?.textContent ?? "", /已经是最新的啦/);
  } finally { await view.cleanup(); }

  resetAppearancePrefsCache();
  const plain = await mountTestComponent(null);
  Object.defineProperty(window, "miraDesktop", { configurable: true, value: { updates: api } });
  window.localStorage.setItem(appearancePrefsStorageKey, JSON.stringify({ version: 1, backdropMotion: true, mascot: false }));
  try {
    await plain.render(<AboutSettingsPage />);
    assert.equal(plain.container.querySelector('[data-testid="about-mascot"]'), null);
    assert.ok(plain.container.querySelector('[aria-label="应用更新"]'));
  } finally {
    await plain.cleanup();
    resetAppearancePrefsCache();
  }
});
