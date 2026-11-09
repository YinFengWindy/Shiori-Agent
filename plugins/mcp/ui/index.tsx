import type { PluginUiModule } from "@yinfengwindy/shiori-sdk";
import { McpSettings } from "./Settings";
/** MCP contributes only its settings page. */
const mcpUi: PluginUiModule = { pluginId: "mcp", settingsSection: { kind: "component", label: "MCP", component: McpSettings } };
export default mcpUi;
