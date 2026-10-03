import type { ComponentType } from "react";
import type { PluginChatImageActionProps, PluginRoleSettingsContribution } from "@yinfengwindy/shiori-sdk";
import { PluginContributionRegistry } from "./pluginContributionRegistry";

/** Role extensions remain registered when disabled so existing saved values survive unrelated edits. */
export const pluginRoleSettingsRegistry = new PluginContributionRegistry<
  PluginRoleSettingsContribution & { pluginId: string }
>("pluginRoleSettings", "role.settings");

/** UI extension only: every operation, label and availability rule belongs to its plugin. */
export const pluginChatImageActionsRegistry = new PluginContributionRegistry<{
  pluginId: string;
  Component: ComponentType<PluginChatImageActionProps>;
}>("pluginChatImageActions", "chat.image.actions");
