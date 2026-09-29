import assert from "node:assert/strict";
import { test } from "node:test";
import { act } from "react";
import type { AccountSnapshot } from "../account/account";
import { mountTestComponent } from "./domTestHarness";
import { createFakeHostUi } from "./fakeHostUi";

const account: AccountSnapshot = {
  id: "qq:101", pluginId: "qq", platform: "qq", platformAccountId: "101", configRef: "aa",
  displayName: "QQ", avatarUrl: "", roleId: "mira", runtimeActive: true, connection: "online",
  capabilities: [], error: "", responseRules: { privateEnabled: true, groupEnabled: true, requireMention: false, blockedSenderIds: [] },
};

const buttonIn = (root: ParentNode, label: string) => Array.from(root.querySelectorAll("button")).find((item) => item.textContent === label);
const cardStatus = (root: ParentNode) => root.querySelector('[aria-label="连接状态"] [aria-live]')?.firstElementChild?.textContent;

test("the stand-in account card reads like the host's and the secondary actions land outside the plugin's markup", async () => {
  const { ui, renders, accountDetailActionsZone } = createFakeHostUi();
  let clicked = 0;
  const view = await mountTestComponent(<>
    <ui.AccountStatusCard account={account} action={{ kind: "disconnect", onClick: () => { clicked += 1; } }} />
    <ui.AccountDetailActions actions={[{ label: "退出登录", onClick: () => undefined, pending: true }]} />
  </>);
  try {
    assert.equal(cardStatus(view.container), "在线");
    await act(async () => buttonIn(view.container, "断开连接")?.click());
    assert.equal(clicked, 1);
    await view.render(<ui.AccountStatusCard account={account} pending="disconnect" action={{ kind: "disconnect", onClick: () => undefined }} />);
    assert.equal(cardStatus(view.container), "正在断开");
    assert.equal(buttonIn(view.container, "断开连接")?.getAttribute("aria-busy"), "true");
    assert.equal(renders.AccountStatusCard.at(-1)?.pending, "disconnect");

    await view.render(<ui.AccountDetailActions actions={[{ label: "退出登录", onClick: () => undefined, pending: true }]} />);
    assert.equal(buttonIn(view.container, "退出登录"), undefined);
    assert.equal(buttonIn(accountDetailActionsZone(), "退出登录")?.disabled, true);
  } finally { await view.cleanup(); }
});
