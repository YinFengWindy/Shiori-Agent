import { TerminalWindow } from "@phosphor-icons/react";
import type { PluginUiModule } from "@yinfengwindy/shiori-sdk";
import { DashboardPage } from "./DashboardPage";
import "./herdr.css";

/** Independent workspace navigation; task creation remains in chat. */
const herdrUi: PluginUiModule = {
  pluginId: "herdr",
  navPage: { label: "Herdr", icon: TerminalWindow, component: DashboardPage, presentation: "workspace" },
  settingsSection: { kind: "schema", label: "Herdr" },
};
export default herdrUi;
