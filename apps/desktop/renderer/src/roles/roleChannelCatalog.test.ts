import assert from "node:assert/strict";
import { describe, it } from "node:test";
import type { ChannelState, ChannelSummary } from "../plugins/pluginBridgeClient";
import {
  defaultRoleBindingChannel,
  roleBindingAvailability,
  roleBindingChannelOptions,
  roleBlockedSenderPlaceholder,
  roleChannelLabel,
} from "./roleChannelCatalog";

function channel(name: string, state: ChannelState, overrides: Partial<ChannelSummary> = {}): ChannelSummary {
  return {
    name, label: name.toUpperCase(), contactLabel: null, chatTypes: [],
    pluginId: name, pluginEnabled: state !== "plugin_disabled", state, error: "", status: null,
    ...overrides,
  };
}

const desktop = channel("desktop", "active", { label: "桌面端", pluginId: null });

describe("roleChannelCatalog", () => {
  it("offers enabled channels with unusable ones marked in the list only, hides disabled plugins and keeps desktop last", () => {
    const catalog = [desktop, channel("telegram", "active", { label: "Telegram" }), channel("qqbot", "not_configured", { label: "QQBot" }), channel("feishu", "failed", { label: "飞书" }), channel("lark", "plugin_disabled")];
    assert.deepEqual(roleBindingChannelOptions(catalog, "telegram"), [
      { value: "telegram", label: "Telegram", triggerLabel: "Telegram" },
      { value: "qqbot", label: "QQBot（未配置）", triggerLabel: "QQBot" },
      { value: "feishu", label: "飞书（异常）", triggerLabel: "飞书" },
      { value: "desktop", label: "桌面端" },
    ]);
  });

  it("offers only the binding's own channel while the catalog loads", () => {
    assert.deepEqual(roleBindingChannelOptions(null, "qqbot"), [{ value: "qqbot", label: "qqbot" }]);
  });

  it("keeps bindings of disabled or uninstalled providers read-only", () => {
    const disabled = channel("qqbot", "plugin_disabled");
    const catalog = [desktop, disabled, channel("demo", "not_configured")];
    assert.deepEqual(roleBindingAvailability({ channel: "qqbot", chat_id: "c2c:1", chat_type: "private", blocked_senders: [] }, catalog), { kind: "plugin_disabled", channel: disabled });
    assert.deepEqual(roleBindingAvailability({ channel: "gone", chat_id: "1", chat_type: "private", blocked_senders: [] }, catalog), { kind: "missing" });
    assert.equal(roleBindingAvailability({ channel: "demo", chat_id: "1", chat_type: "private", blocked_senders: [] }, catalog).kind, "editable");
    assert.equal(roleBindingAvailability({ channel: "desktop", chat_id: "role:mira", chat_type: "private", blocked_senders: [] }, catalog).kind, "editable");
    // Nothing is known yet, so nothing may be locked.
    assert.deepEqual(roleBindingAvailability({ channel: "qqbot", chat_id: "c2c:1", chat_type: "private", blocked_senders: [] }, null), { kind: "editable", channel: null });
  });

  it("defaults a new binding to a working external channel, then any enabled one, then desktop", () => {
    assert.equal(defaultRoleBindingChannel([desktop, channel("qqbot", "not_configured"), channel("telegram", "active")]), "telegram");
    assert.equal(defaultRoleBindingChannel([desktop, channel("qqbot", "plugin_disabled"), channel("demo", "failed")]), "demo");
    assert.equal(defaultRoleBindingChannel([desktop, channel("qqbot", "plugin_disabled")]), "desktop");
  });

  it("labels fields from the channel declaration", () => {
    const qqbot = channel("qqbot", "active", { label: "QQBot", contactLabel: "QQBot 用户 OpenID" });
    assert.equal(roleChannelLabel("qqbot", [qqbot]), "QQBot");
    assert.equal(roleChannelLabel("desktop", null), "桌面端");
    assert.equal(roleChannelLabel("gone", [qqbot]), "gone");
    assert.equal(roleBlockedSenderPlaceholder(qqbot), "QQBot 用户 OpenID");
    assert.equal(roleBlockedSenderPlaceholder(null), "");
  });
});
