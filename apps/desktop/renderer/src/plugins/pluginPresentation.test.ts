import assert from "node:assert/strict";
import { describe, it } from "node:test";
import type { PluginSummary } from "./pluginBridgeClient";
import { groupPlugins, pluginDisplayName, pluginProblem, pluginStateLabel, prettifyPluginId } from "./pluginPresentation";

function plugin(overrides: Partial<PluginSummary>): PluginSummary {
  return {
    id: "demo", candidateId: "builtin/demo", source: "builtin", directory: "plugins/demo", name: "demo", version: "0.1.0",
    description: "", enabled: true, canToggle: true, state: "ACTIVE", error: "", diagnostic: null, hasConfigSchema: false,
    capabilities: [], channels: [], category: "feature", supportsHotUnload: true, pendingRendererKinds: [],
    ...overrides,
  };
}

describe("pluginPresentation", () => {
  it("groups the roster into 功能 / 渠道 / 系统组件 by manifest category, dropping empty groups", () => {
    const groups = groupPlugins([
      plugin({ id: "guard", category: "system" }),
      plugin({ id: "telegram", category: "channel" }),
      plugin({ id: "story" }),
      plugin({ id: "pet" }),
    ]);
    assert.deepEqual(groups.map((group) => [group.title, group.collapsible, group.plugins.map((item) => item.id)]), [
      ["功能", false, ["story", "pet"]],
      ["渠道", false, ["telegram"]],
      ["系统组件", true, ["guard"]],
    ]);
    assert.deepEqual(groupPlugins([plugin({ id: "only" })]).map((group) => group.category), ["feature"]);
  });

  it("shows the manifest display name, and word-cases a bare id instead of showing it raw", () => {
    assert.equal(pluginDisplayName({ id: "qqbot", name: "QQBot" }), "QQBot");
    assert.equal(pluginDisplayName({ id: "tool_loop_guard", name: "tool_loop_guard" }), "Tool Loop Guard");
    assert.equal(prettifyPluginId("shell-restore"), "Shell Restore");
  });

  it("turns diagnostic states into one readable line and keeps untrusted plugins problem-free", () => {
    assert.equal(pluginProblem(plugin({})), null);
    assert.equal(pluginProblem(plugin({ state: "FAILED", error: "ModuleNotFoundError: httpx" })), "启动失败");
    assert.equal(pluginProblem(plugin({ state: "CONFLICT" })), "与另一个同 ID 的插件冲突，两者都已停用");
    assert.equal(
      pluginProblem(plugin({ state: "BLOCKED", diagnostic: { code: "missing_dependency", stage: "dependencies", field: "dependencies", reason: "x", path: "", state: "BLOCKED" } })),
      "无法加载：缺少它依赖的插件",
    );
    assert.equal(pluginProblem(plugin({ rendererError: "boom" })), "界面加载失败");
    assert.equal(pluginProblem(plugin({ state: "UNTRUSTED", error: "外部插件尚未获得信任" })), null);
    assert.equal(pluginProblem(plugin({ state: "DISABLED", error: "trust saved", trustPendingRestart: true })), null);
  });

  it("labels transitional states without echoing raw state names", () => {
    assert.equal(pluginStateLabel(plugin({})), null);
    assert.equal(pluginStateLabel(plugin({ pendingOperation: "update" })), "待重启 · 更新");
    assert.equal(pluginStateLabel(plugin({ state: "UNTRUSTED" })), "未信任");
    assert.equal(pluginStateLabel(plugin({ pendingRendererKinds: ["ui"] })), "激活中…");
  });
});
