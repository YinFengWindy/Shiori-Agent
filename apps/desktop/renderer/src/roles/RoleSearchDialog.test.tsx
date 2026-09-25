/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { appearancePrefsStorageKey } from "../shared/appearancePrefs";
import { mountTestComponent } from "../shared/testing/domTestHarness";
import { resetAppearancePrefsCache } from "../shared/useAppearancePrefs";
import { RoleSearchDialog } from "./RoleSearchDialog";

function dialog(query: string, searching = false) {
  return (
    <RoleSearchDialog open query={query} searching={searching} results={[]}
      onClose={() => undefined} onSelectResult={() => undefined} onUpdateQuery={() => undefined} />
  );
}

const emptyOf = (container: HTMLElement) => container.querySelector('[data-testid="role-search-empty"]');

describe("RoleSearchDialog", () => {
  it("has 吟风 say 没找到 for a query without results, but not before one is typed or while searching", async () => {
    resetAppearancePrefsCache();
    const view = await mountTestComponent(dialog(""));
    try {
      assert.match(emptyOf(view.container)?.textContent ?? "", /搜索角色名或消息内容/);
      await view.render(dialog("凛", true));
      assert.equal(emptyOf(view.container)?.querySelector('[data-testid="mascot-medium"]'), null);
      await view.render(dialog("凛"));
      assert.equal(emptyOf(view.container)?.querySelector('[data-testid="mascot-medium"]')?.getAttribute("data-expression"), "confused");
      assert.match(emptyOf(view.container)?.textContent ?? "", /没找到耶/);
    } finally {
      await view.cleanup();
    }
  });

  it("keeps the plain 没有找到匹配结果 with the 看板娘 off", async () => {
    resetAppearancePrefsCache();
    const view = await mountTestComponent(<div />);
    try {
      window.localStorage.setItem(appearancePrefsStorageKey, JSON.stringify({ version: 1, backdropMotion: true, mascot: false }));
      await view.render(dialog("凛"));
      assert.equal(emptyOf(view.container)?.textContent, "没有找到匹配结果");
    } finally {
      await view.cleanup();
      resetAppearancePrefsCache();
    }
  });
});
