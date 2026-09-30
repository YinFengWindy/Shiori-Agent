import assert from "node:assert/strict";
import { test } from "node:test";
import { mountTestComponent } from "@shiori/plugin-sdk/testing";
import type { AccountSnapshot } from "@shiori/plugin-sdk";
import { AccountStatusCard } from "./AccountStatusCard";

const account: AccountSnapshot = {
  id: "a", pluginId: "demo", platform: "demo", platformAccountId: "101", configRef: "demo",
  displayName: "Demo", avatarUrl: "", roleId: "role-1",
  runtimeActive: true, connection: "online", capabilities: [], error: "",
  responseRules: { privateEnabled: true, groupEnabled: true, requireMention: true, blockedSenderIds: [] },
};

const noop = () => undefined;
const words = (root: ParentNode) => root.querySelector("[aria-live]")?.firstElementChild?.textContent;

test("the card reads the host status unless the plugin knows better, and shows an in-flight command at once", async () => {
  const view = await mountTestComponent(<AccountStatusCard account={account} action={{ kind: "disconnect", onClick: noop }} />);
  try {
    assert.equal(words(view.container), "在线");
    assert.equal(view.container.querySelector("button")?.textContent, "断开连接");
    await view.render(<AccountStatusCard account={null} action={{ kind: "connect", onClick: noop }} />);
    assert.equal(words(view.container), "未连接");
    await view.render(<AccountStatusCard account={account} status={{ label: "等待扫码登录", tone: "warning" }}
      detail="NapCat v4" action={{ kind: "connect", onClick: noop }} />);
    assert.equal(words(view.container), "等待扫码登录");
    assert.match(view.container.textContent ?? "", /NapCat v4/);
    await view.render(<AccountStatusCard account={account} pending="disconnect" status={{ label: "在线", tone: "success" }}
      action={{ kind: "disconnect", onClick: noop }} />);
    assert.equal(words(view.container), "正在断开");
    const button = view.container.querySelector("button");
    assert.equal(button?.disabled, true);
    assert.equal(button?.getAttribute("aria-busy"), "true");
    assert.ok(button?.querySelector("svg.animate-spin.motion-reduce\\:animate-none"));
  } finally { await view.cleanup(); }
});

test("the host's own failure report shows inside the card", async () => {
  const view = await mountTestComponent(<AccountStatusCard account={{ ...account, connection: "error", error: "token revoked" }} />);
  try {
    assert.equal(words(view.container), "故障");
    assert.equal(view.container.querySelector('[role="alert"]')?.textContent?.includes("token revoked"), true);
  } finally { await view.cleanup(); }
});
