import { TerminalWindow } from "@phosphor-icons/react";
import type { PluginUiModule } from "@yinfengwindy/shiori-sdk";
import { DashboardPage } from "./DashboardPage";
import { HerdrSettingsPage } from "./Settings";
import { AgentSidebar } from "./AgentSidebar";

/** Herdr's workspace: the session's agents and plugin tasks in the host's secondary sidebar, the selected one in the page. Tasks start in chat. */
const herdrUi: PluginUiModule = {
  pluginId: "herdr",
  navPage: { label: "Herdr", icon: TerminalWindow, component: DashboardPage, sidebar: AgentSidebar, presentation: "workspace" },
  settingsSection: { kind: "component", label: "Herdr", component: HerdrSettingsPage },
};
export default herdrUi;
