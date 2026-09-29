import type { RoleRecord } from "../domain/role";
import type { BridgeEvent } from "../rpc";
import type { PluginHostFeedback } from "./feedback";
import type { NativeFilePickerOptions } from "./filePicker";
import type { PluginHostUi } from "./hostUi";

/**
 * Narrow host services available to plugin UI without exposing raw IPC: the
 * injected `host` prop of every bound plugin component.
 */
export type PluginHostServices = {
  /** Subscribes to every desktop bridge event; returns the unsubscribe function. */
  onEvent: (listener: (event: BridgeEvent) => void) => () => void;
  listRoles: () => Promise<RoleRecord[]>;
  pickImages: (options: { multiple: boolean }) => Promise<string[]>;
  /** Native user selection plus bounded private staging, without a media grant. */
  pickFiles: (options: NativeFilePickerOptions) => Promise<string[]>;
  /** Toasts in the host queue; `persona` (true or a scene key) lets 吟风 front one (runtime API 2.4.0). */
  feedback: PluginHostFeedback;
  /** Host components (runtime API 2.4.0). */
  ui: PluginHostUi;
};
