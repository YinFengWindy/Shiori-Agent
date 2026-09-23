import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { act } from "react";
import { mountTestComponent } from "../shared/testing/domTestHarness";
import { BridgeOfflineBanner, shouldShowBridgeOfflineBanner } from "./BridgeOfflineBanner";

describe("shouldShowBridgeOfflineBanner", () => {
  it("stays hidden during the first connect and while online", () => {
    assert.equal(shouldShowBridgeOfflineBanner("connecting", false), false);
    assert.equal(shouldShowBridgeOfflineBanner("online", false), false);
  });

  it("shows while offline and across a restart the banner itself started", () => {
    assert.equal(shouldShowBridgeOfflineBanner("offline", false), true);
    assert.equal(shouldShowBridgeOfflineBanner("connecting", true), true);
  });
});

describe("BridgeOfflineBanner", () => {
  it("restarts the bridge from its button and disables it until the restart settles", async () => {
    let finish!: () => void;
    let restarts = 0;
    const onRestart = () => {
      restarts += 1;
      return new Promise<void>((resolve) => { finish = resolve; });
    };
    const view = await mountTestComponent(<BridgeOfflineBanner health="offline" bridgeError={"bridge exited with code 1\ntraceback"} onRestart={onRestart} />);
    try {
      const button = view.container.querySelector("button")!;
      assert.match(view.container.textContent ?? "", /连接已断开/);
      assert.equal(view.container.querySelector("[title]")?.getAttribute("title"), "bridge exited with code 1");
      await act(async () => button.click());
      assert.equal(restarts, 1);
      assert.equal(button.disabled, true);
      assert.match(view.container.textContent ?? "", /正在重新连接/);
      await act(async () => finish());
      assert.equal(button.disabled, false);
    } finally { await view.cleanup(); }
  });

  it("renders nothing while the bridge is online", async () => {
    const view = await mountTestComponent(<BridgeOfflineBanner health="online" bridgeError="" onRestart={async () => undefined} />);
    try {
      assert.equal(view.container.innerHTML, "");
    } finally { await view.cleanup(); }
  });
});
