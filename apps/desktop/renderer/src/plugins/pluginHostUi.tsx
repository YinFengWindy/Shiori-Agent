import { InlineError, type InlineErrorProps } from "../shared/feedback/InlineError";
import { confirmPersonaLines, personaSceneLines } from "../shared/mascot/mascotLines";
import { ConfirmDialog, type ConfirmDialogProps } from "../shared/ui/ConfirmDialog";
import type { PluginPersona } from "./pluginHostFeedback";

/*
 * Host components for plugin UIs (runtime API 2.4.0), reached through
 * `PluginHostServices.ui`. Both take a `PluginPersona` (see
 * pluginHostFeedback.ts): default false, `true` / `"generic"` for the
 * component's generic line, or a scene key for the host's line for it.
 */

/** Props of `PluginHostServices.ui.InlineError`: the host block, with a plugin persona. */
export type HostInlineErrorProps = Omit<InlineErrorProps, "persona"> & {
  /** Let 吟风 front the block: generically or by scene. Default false. */
  persona?: PluginPersona;
};

/** The host's in-page error block for plugin UIs (`PluginHostServices.ui.InlineError`). */
export function HostInlineError({ persona = false, ...props }: HostInlineErrorProps) {
  return <InlineError {...props} persona={!persona ? false : persona === true || persona === "generic" ? "generic" : persona} />;
}

/** Props of `PluginHostServices.ui.ConfirmDialog`: the host dialog, with a plugin persona. */
export type HostConfirmDialogProps = Omit<ConfirmDialogProps, "persona"> & {
  /**
   * Let 吟风 lead the dialog. `true` / `"generic"` picks the host's generic
   * line for a destructive or an ordinary confirmation; a scene key (usually
   * `destructive`, `discard` or `confirm`) that scene's line. Default false.
   */
  persona?: PluginPersona;
};

/** The host's confirmation dialog for plugin UIs (`PluginHostServices.ui.ConfirmDialog`). */
export function HostConfirmDialog({ persona = false, destructive = true, ...props }: HostConfirmDialogProps) {
  const generic = destructive ? confirmPersonaLines.destructive : confirmPersonaLines.confirm;
  const line = !persona ? undefined : persona === true || persona === "generic" ? generic : personaSceneLines[persona];
  return <ConfirmDialog {...props} destructive={destructive} persona={line} />;
}
