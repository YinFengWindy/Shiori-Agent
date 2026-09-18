import { useMemo, useState } from "react";
import type { PluginSummary } from "./pluginBridgeClient";
import { createPluginPackageClient, type PluginPackagePreview } from "./pluginPackageClient";
import type { usePluginManagementController } from "./usePluginManagementController";

/** Owns package confirmation dialogs and shares management's mutation/refresh boundary. */
export function usePluginPackageController(runMutation: ReturnType<typeof usePluginManagementController>["runMutation"]) {
  const client = useMemo(() => createPluginPackageClient(), []);
  const [preview, setPreview] = useState<PluginPackagePreview | null>(null);
  const [uninstallCandidate, setUninstallCandidate] = useState<PluginSummary | null>(null);
  const [deleteData, setDeleteData] = useState(false);
  const [busy, setBusy] = useState(false);

  const run = async (id: string, action: () => Promise<unknown>) => {
    setBusy(true);
    try { return await runMutation(id, action); }
    finally { setBusy(false); }
  };

  return {
    preview, uninstallCandidate, deleteData, setDeleteData, busy,
    pickPackage: (candidate?: PluginSummary) => run(candidate?.id ?? "$install", async () => {
      setPreview(await client.pickPackage(candidate?.candidateId));
    }),
    confirm: () => preview && run(preview.id, async () => {
      await client.confirm(preview.token);
      setPreview(null);
    }),
    cancel: () => preview && run(preview.id, async () => {
      await client.cancel(preview.token);
      setPreview(null);
    }),
    requestUninstall: (candidate: PluginSummary) => { setDeleteData(false); setUninstallCandidate(candidate); },
    closeUninstall: () => setUninstallCandidate(null),
    uninstall: () => uninstallCandidate && run(uninstallCandidate.id, async () => {
      await client.uninstall(uninstallCandidate.candidateId, deleteData);
      setUninstallCandidate(null);
    }),
  };
}
