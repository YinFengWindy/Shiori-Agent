import assert from "node:assert/strict";
import { afterEach, before, describe, it } from "node:test";
import { appearancePrefsStorageKey } from "../shared/appearancePrefs";
import { confirmPersonaLines, inlineErrorLines, personaSceneLines } from "../shared/mascot/mascotLines";
import { mountTestComponent } from "../shared/testing/domTestHarness";
import { resetAppearancePrefsCache } from "../shared/useAppearancePrefs";

let HostInlineError: typeof import("./pluginHostUi").HostInlineError;
let HostConfirmDialog: typeof import("./pluginHostUi").HostConfirmDialog;
let desktopPluginHostServices: typeof import("./pluginHostServices").desktopPluginHostServices;
before(async () => {
  // Base UI's dialog needs a DOM before it is imported (so do the host services, which import it).
  const view = await mountTestComponent(null);
  ({ HostInlineError, HostConfirmDialog } = await import("./pluginHostUi"));
  ({ desktopPluginHostServices } = await import("./pluginHostServices"));
  await view.cleanup();
});

afterEach(() => resetAppearancePrefsCache());

/** A fresh window with 设置 › 外观 › 看板娘 set to `mascot`. */
async function mountWithMascot(mascot: boolean) {
  const view = await mountTestComponent(null);
  resetAppearancePrefsCache();
  window.localStorage.setItem(appearancePrefsStorageKey, JSON.stringify({ version: 1, backdropMotion: true, mascot }));
  return view;
}

const noop = () => undefined;

describe("plugin host UI (runtime API 2.4.0)", () => {
  it("is what the host services hand to plugins", () => {
    assert.equal(desktopPluginHostServices.ui.InlineError, HostInlineError);
    assert.equal(desktopPluginHostServices.ui.ConfirmDialog, HostConfirmDialog);
  });

  it("gives plugins the host inline error: plain by default, generic on true, the scene's line on a key", async () => {
    const view = await mountWithMascot(true);
    const line = () => view.container.querySelector('[data-testid="inline-error-line"]')?.textContent;
    try {
      await view.render(<HostInlineError message="加载失败" />);
      assert.equal(view.container.querySelector('[data-testid="mascot-face"]'), null, "persona defaults to off for plugins");
      await view.render(<HostInlineError persona message="加载失败" />);
      assert.equal(line(), inlineErrorLines.generic.text);
      await view.render(<HostInlineError persona="generic" message="加载失败" />);
      assert.equal(line(), inlineErrorLines.generic.text);
      await view.render(<HostInlineError persona="quota" message="额度不足" />);
      assert.equal(line(), personaSceneLines.quota.text);
      assert.equal(view.container.querySelector('[role="alert"]')?.getAttribute("data-persona"), "quota");
    } finally { await view.cleanup(); }
    const off = await mountWithMascot(false);
    try {
      await off.render(<HostInlineError persona="network" message="加载失败" />);
      assert.equal(off.container.querySelector('[data-testid="mascot-face"]'), null);
      assert.equal(off.container.querySelector('[role="alert"]')?.textContent, "加载失败");
    } finally { await off.cleanup(); }
  });

  it("gives plugins the host confirmation: plain by default, generic by intent on true, the scene's line on a key", async () => {
    const lead = () => document.querySelector('[data-testid="confirm-persona"] [data-testid="mascot-line"]')?.textContent ?? null;
    const cases: Array<[Parameters<typeof HostConfirmDialog>[0]["persona"], boolean, string | null]> = [
      [undefined, true, null],
      [true, true, confirmPersonaLines.destructive.text],
      [true, false, confirmPersonaLines.confirm.text],
      ["discard", true, personaSceneLines.discard.text],
    ];
    for (const [persona, destructive, expected] of cases) {
      const view = await mountWithMascot(true);
      try {
        await view.render(<HostConfirmDialog open persona={persona} destructive={destructive} title="删除提示词" description="删除后无法恢复。" confirmLabel="删除" onClose={noop} onConfirm={noop} />);
        const text = lead();
        assert.equal(text === null ? null : text.replace(/^吟风/, ""), expected, String(persona));
      } finally { await view.cleanup(); }
    }
    const off = await mountWithMascot(false);
    try {
      await off.render(<HostConfirmDialog open persona="destructive" title="删除提示词" description="删除后无法恢复。" confirmLabel="删除" onClose={noop} onConfirm={noop} />);
      assert.equal(document.querySelector('[data-testid="confirm-persona"]'), null);
    } finally { await off.cleanup(); }
  });
});
