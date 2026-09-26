import assert from "node:assert/strict";
import { test } from "node:test";
import type { ChannelSummary } from "../plugins/pluginBridgeClient";
import { roleChannelLabel } from "./roleChannelCatalog";

test("chat source labels use live channel names and retain unknown historical names", () => {
  const catalog = [{ name: "qq", label: "QQ" }] as ChannelSummary[];
  assert.equal(roleChannelLabel("qq", catalog), "QQ");
  assert.equal(roleChannelLabel("desktop", null), "桌面端");
  assert.equal(roleChannelLabel("retired-plugin", catalog), "retired-plugin");
});
