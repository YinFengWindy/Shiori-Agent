import { createRoot } from "react-dom/client";
import { PluginBridgeError } from "@shiori/plugin-sdk";
import { initializeRuntimePluginUi } from "../../renderer/src/plugins/runtimePluginUiBootstrap";
import { refreshPluginEnabledState } from "../../renderer/src/plugins/pluginEnabledStateStore";
import { pluginUiRegistry } from "../../renderer/src/plugins/pluginUiRegistry";

initializeRuntimePluginUi();
const root = createRoot(document.getElementById("root")!);
const refresh = async () => {
  const plugins = await refreshPluginEnabledState();
  const entry = pluginUiRegistry.getNavPage("demo");
  root.render(entry ? <entry.Component pageId="demo" /> : <p>No plugin UI</p>);
  return plugins;
};
// The host's SDK class, compared with what the precompiled plugin imported.
Object.assign(globalThis, { refreshPluginUiQa: refresh, hostPluginBridgeError: PluginBridgeError });
void refresh();
