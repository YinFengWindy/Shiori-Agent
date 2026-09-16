import type { ComponentType } from "react";
import type { ChatImageHistoryEntry } from "../chat/chatImageHistory";
import type { SessionMessageUpdatePayload } from "../shared/types";
import { PluginContributionRegistry } from "./pluginContributionRegistry";
import type { PluginRpcClient } from "./pluginBridgeClient";

/** One plugin's editable role values; the plugin owns their schema and persistence keys. */
export type PluginRoleValues = Record<string, unknown>;

/** Props for a plugin-owned section within the role capabilities editor. */
export type PluginRoleSettingsProps = {
  values: PluginRoleValues;
  /** Latest plugin-owned projection, distinct from the editable draft. */
  snapshot?: PluginRoleValues;
  disabled?: boolean;
  onChange: (values: PluginRoleValues) => void;
};

/** A role contribution shares the explicit Save action, with its own storage owner. */
export type PluginRoleSettingsContribution = {
  read: (source: Record<string, unknown>) => PluginRoleValues;
  Component: ComponentType<PluginRoleSettingsProps>;
  /** Runs only after a successful save changed this contribution's values. */
  afterSave?: (values: PluginRoleValues, client: PluginRpcClient) => Promise<void>;
} & (
  | { storage?: "runtime"; write: (runtimeConfig: Record<string, unknown>, values: PluginRoleValues) => Record<string, unknown> }
  | { storage: "plugin" }
);

/** Identifies an existing message image without exposing the host's mutable session state. */
export type PluginImageTarget = ChatImageHistoryEntry & { sessionKey: string };

/** Context supplied to a plugin-owned action in the chat image lightbox. */
export type PluginChatImageActionProps = {
  target: PluginImageTarget;
  client: PluginRpcClient;
  onSessionUpdate: (sessionKey: string, update: SessionMessageUpdatePayload) => void;
  onError: (message: string) => void;
  onNotice: (message: string) => void;
};

/** Role extensions remain registered when disabled so existing saved values survive unrelated edits. */
export const pluginRoleSettingsRegistry = new PluginContributionRegistry<
  PluginRoleSettingsContribution & { pluginId: string }
>("pluginRoleSettings", "role.settings");

/** UI extension only: every operation, label and availability rule belongs to its plugin. */
export const pluginChatImageActionsRegistry = new PluginContributionRegistry<{
  pluginId: string;
  Component: ComponentType<PluginChatImageActionProps>;
}>("pluginChatImageActions", "chat.image.actions");
