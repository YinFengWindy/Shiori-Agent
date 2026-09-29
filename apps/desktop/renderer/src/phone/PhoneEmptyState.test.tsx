import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { appearancePrefsStorageKey } from "../shared/appearancePrefs";
import { emptyStateLines } from "../shared/mascot/mascotLines";
import { mountTestComponent } from "../shared/testing/domTestHarness";
import { resetAppearancePrefsCache } from "../shared/useAppearancePrefs";
import { PhoneEmptyState } from "./PhoneEmptyState";

const emptyState = <PhoneEmptyState line={emptyStateLines.phoneNoAccounts} label="还没有账号" testId="empty" />;

describe("PhoneEmptyState", () => {
  it("has 吟风 say it with the 看板娘 on (the default)", async () => {
    resetAppearancePrefsCache();
    const view = await mountTestComponent(emptyState);
    try {
      const empty = view.container.querySelector('[data-testid="empty"]');
      assert.equal(empty?.querySelector('[data-testid="mascot-medium"]')?.getAttribute("data-expression"), "smug");
      assert.match(empty?.textContent ?? "", /手机里一个号都没有/);
    } finally { await view.cleanup(); }
  });

  it("shows the plain label without her with the 看板娘 off", async () => {
    resetAppearancePrefsCache();
    const view = await mountTestComponent(<div />);
    try {
      window.localStorage.setItem(appearancePrefsStorageKey, JSON.stringify({ version: 1, backdropMotion: true, mascot: false }));
      await view.render(emptyState);
      const empty = view.container.querySelector('[data-testid="empty"]');
      assert.equal(empty?.querySelector('[data-testid="mascot-medium"]'), null);
      assert.equal(empty?.textContent, "还没有账号");
    } finally {
      await view.cleanup();
      resetAppearancePrefsCache();
    }
  });
});
