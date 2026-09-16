import assert from "node:assert/strict";
import { test } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import { PluginChatImageActions } from "./PluginChatImageActions";
import { pluginChatImageActionsRegistry } from "./pluginFeatureRegistry";
import { resetPluginEnabledStateForTests, setPluginEnabledSnapshot } from "./pluginEnabledStateStore";

test("plugin action slots disappear for disabled or dependency-blocked plugins", () => {
  pluginChatImageActionsRegistry.register({ pluginId: "sample",
    Component: () => <button>Sample action</button>,
  });
  const render = () => renderToStaticMarkup(<PluginChatImageActions
    target={{ sessionKey: "session", historyKey: "image", path: "image.png", messageId: "m", mediaIndex: 0, timestamp: null }}
    onError={() => {}} onNotice={() => {}} onSessionUpdate={() => {}} />);
  try {
    setPluginEnabledSnapshot([{ id: "sample", enabled: true, state: "ACTIVE" }]);
    assert.match(render(), /Sample action/);
    setPluginEnabledSnapshot([{ id: "sample", enabled: true, state: "BLOCKED" }]);
    assert.doesNotMatch(render(), /Sample action/);
    setPluginEnabledSnapshot([{ id: "sample", enabled: false, state: "DISABLED" }]);
    assert.doesNotMatch(render(), /Sample action/);
  } finally {
    pluginChatImageActionsRegistry.unregister("sample");
    resetPluginEnabledStateForTests();
  }
});
