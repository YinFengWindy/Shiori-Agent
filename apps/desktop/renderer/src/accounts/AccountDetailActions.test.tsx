import assert from "node:assert/strict";
import { test } from "node:test";
import { mountTestComponent } from "@shiori/plugin-sdk/testing";
import { AccountDetailActions, AccountDetailActionsTarget } from "./AccountDetailActions";

const actions = [{ label: "退出登录", onClick: () => undefined }];

test("plugin secondary actions land in the dialog's danger zone and render nothing outside a dialog", async () => {
  const view = await mountTestComponent(<AccountDetailActions actions={actions} />);
  try {
    assert.equal(view.container.querySelector("button"), null);
    const zone = document.createElement("div");
    document.body.append(zone);
    await view.render(<AccountDetailActionsTarget value={zone}>
      <section><AccountDetailActions actions={[{ ...actions[0], pending: true }]} /></section>
    </AccountDetailActionsTarget>);
    assert.equal(view.container.querySelector("button"), null);
    const button = zone.querySelector("button");
    assert.equal(button?.textContent, "退出登录");
    assert.equal(button?.disabled, true);
    assert.equal(button?.getAttribute("aria-busy"), "true");
  } finally { await view.cleanup(); }
});
