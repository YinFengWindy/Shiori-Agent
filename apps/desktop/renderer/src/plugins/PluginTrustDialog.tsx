import type { PluginSummary } from "./pluginBridgeClient";
import { confirmPersonaLines } from "../shared/mascot/mascotLines";
import { ConfirmDialog } from "../shared/ui/ConfirmDialog";
import { pluginTrustDisclosure } from "./pluginTrustDisclosure";

/** Explicit trust confirmation for the displayed package identity and content snapshot. */
export function PluginTrustDialog({ plugin, enable = false, busy, confirmDisabled = false, error, onClose, onConfirm }: {
  plugin: PluginSummary | null; enable?: boolean; busy: boolean; confirmDisabled?: boolean; error: string; onClose: () => void; onConfirm: () => void;
}) {
  return <ConfirmDialog busyLabel="处理中…" destructive={false} open={plugin !== null} title="信任插件" persona={confirmPersonaLines.trustPlugin} description={pluginTrustDisclosure}
    confirmLabel={enable ? "信任并启用" : "确认信任"} confirmDisabled={confirmDisabled} busy={busy} error={error} onClose={onClose} onConfirm={onConfirm}>
    <div className="grid gap-1 text-body text-ink-secondary">
      <div>{plugin?.name} · {plugin?.version}</div>
      <div className="break-all">{plugin?.trustDirectory || plugin?.directory}</div>
    </div>
  </ConfirmDialog>;
}
