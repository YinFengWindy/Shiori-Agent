/** Contracts of the role settings and chat image action contributions. */
import type { ComponentType } from "react";
import type { ChatImageHistoryEntry, SessionMessageUpdatePayload } from "../domain/session";
import type { PluginRpcClient } from "../rpc";

/** One plugin's editable role values; the plugin owns their schema and persistence keys. */
export type PluginRoleValues = Record<string, unknown>;

/** Props for a plugin-owned section within the role capabilities editor. */
export type PluginRoleSettingsProps = {
  /**
   * The edited role, null while a new one is being created (runtime API
   * 3.1.11). With `client` and the injected host services it lets the card's
   * settings dialog own plugin-private, autosaved settings (`usePrivateAutosave`)
   * beside the role draft in `values`.
   */
  roleId: string | null;
  /** The plugin's scoped RPC client (runtime API 3.1.11). */
  client: PluginRpcClient;
  /**
   * The moods of the edited role's draft (runtime API 3.1.14), e.g. to offer
   * per-mood settings.
   */
  moodCatalog: readonly string[];
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
