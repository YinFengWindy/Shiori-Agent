import type { HostConfirmDialogProps, HostInlineErrorProps } from "@shiori/plugin-sdk";
import { InlineError } from "../shared/feedback/InlineError";
import { confirmPersonaLines, personaSceneLines } from "../shared/mascot/mascotLines";
import { ConfirmDialog } from "../shared/ui/ConfirmDialog";

/** The host's in-page error block for plugin UIs (`PluginHostServices.ui.InlineError`). */
export function HostInlineError({ persona = false, ...props }: HostInlineErrorProps) {
  return <InlineError {...props} persona={!persona ? false : persona === true || persona === "generic" ? "generic" : persona} />;
}

/** The host's confirmation dialog for plugin UIs (`PluginHostServices.ui.ConfirmDialog`). */
export function HostConfirmDialog({ persona = false, destructive = true, ...props }: HostConfirmDialogProps) {
  const generic = destructive ? confirmPersonaLines.destructive : confirmPersonaLines.confirm;
  const line = !persona ? undefined : persona === true || persona === "generic" ? generic : personaSceneLines[persona];
  return <ConfirmDialog {...props} destructive={destructive} persona={line} />;
}
