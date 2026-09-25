import { useCallback, useEffect, useState } from "react";
import { usePluginHostServices } from "../../../apps/desktop/renderer/src/plugins/PluginHostServicesProvider";
import type { PluginRoleAssetsComponentProps } from "../../../apps/desktop/renderer/src/plugins/pluginUiModuleContract";
import { noPetPackages, readPetPackages, type PetPackages } from "./petPackages";
import { pickPetPackageFile } from "./petPackagePicker";

/** Loads and mutates this role's packages, then refreshes both form and pet projections. */
export function usePetPackages({ roleId, disabled, client, onRoleDataChanged }: Omit<PluginRoleAssetsComponentProps, "host">) {
  const { pickFiles } = usePluginHostServices();
  const [state, setState] = useState<PetPackages>(noPetPackages);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const parse = useCallback(
    (payload: unknown) => readPetPackages(payload, (path) => window.miraDesktop.localAssetUrl(path)),
    [],
  );

  // `disabled` is a dependency on purpose: it falls when the bridge comes up
  // or a host save finishes, and a list that failed during either needs a
  // second chance. Without it one transient refusal — `pets.list` is not
  // admission-exempt, so a channel-config reload answers `runtime_reloading` —
  // leaves the panel blank with a red line until the user navigates away.
  useEffect(() => {
    if (!roleId) {
      setState(noPetPackages);
      return;
    }
    let alive = true;
    void (async () => {
      try {
        const next = parse(await client.call<unknown>("pets.list", { role_id: roleId }));
        if (!alive) return;
        setState(next);
        setError("");
      } catch (reason) {
        if (!alive) return;
        // The previous rows are kept: a failed refresh is not evidence that the
        // packages are gone, and blanking the list would make a momentary
        // bridge hiccup look like data loss.
        setError(reason instanceof Error ? reason.message : String(reason));
      }
    })();
    return () => { alive = false; };
  }, [client, disabled, parse, roleId]);

  /** Runs one mutation, surfacing its failure instead of leaving the panel silent. */
  const run = useCallback(async (action: () => Promise<void>) => {
    setBusy(true);
    try {
      await action();
      setError("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setBusy(false);
    }
  }, []);

  const mutate = useCallback(async (method: "pets.import" | "pets.remove" | "pets.select", payload: Record<string, unknown>) => {
    setState(parse(await client.call<unknown>(method, { role_id: roleId, ...payload })));
    onRoleDataChanged();
    if (method !== "pets.import") await client.background.call("sync");
  }, [client, onRoleDataChanged, parse, roleId]);

  const onImport = useCallback(() => void run(async () => {
    const source = await pickPetPackageFile(pickFiles);
    if (source) await mutate("pets.import", { source });
  }), [mutate, pickFiles, run]);

  const onRemove = useCallback((packageId: string) => void run(() => mutate("pets.remove", { package_id: packageId })), [mutate, run]);
  const onSelect = useCallback((packageId: string) => void run(() => mutate("pets.select", { package_id: packageId })), [mutate, run]);

  return { state, busy, error, onImport, onRemove, onSelect };
}
