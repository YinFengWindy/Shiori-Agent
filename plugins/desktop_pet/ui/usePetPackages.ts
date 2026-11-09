import { rpcMethods } from "../rpcMethods.generated";
import { useCallback, useEffect, useState } from "react";
import { errorMessage, type HostInlineErrorProps, usePluginHostServices, type PluginRoleAssetsComponentProps } from "@yinfengwindy/shiori-sdk";
import { noPetPackages, readPetPackages, type PetPackages } from "./petPackages";
import { pickPetPackageFile } from "./petPackagePicker";
import type { PetPackageProvider } from "./petPackages";
import type { PetModelReference } from "@yinfengwindy/shiori-pet";

/** Loads and mutates this role's packages, then refreshes both form and pet projections. */
export function usePetPackages({ roleId, disabled, client, onRoleDataChanged }: Omit<PluginRoleAssetsComponentProps, "host">) {
  const { pickFiles, assets } = usePluginHostServices();
  const [state, setState] = useState<PetPackages>(noPetPackages);
  const [busy, setBusy] = useState(false);
  // The role whose first read has answered (rows or an error); until then the panel shows it is loading.
  const [answeredRole, setAnsweredRole] = useState<string | null>(null);
  const [error, setError] = useState<Pick<HostInlineErrorProps, "message" | "detail"> | null>(null);

  const parse = useCallback(
    (payload: unknown) => readPetPackages(payload, (path) => assets.url(path)),
    [assets],
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
        const next = parse(await client.call<unknown>(rpcMethods["pets.list"], { role_id: roleId }));
        if (!alive) return;
        setState(next);
        setError(null);
        setAnsweredRole(roleId);
      } catch (reason) {
        if (!alive) return;
        // The previous rows are kept: a failed refresh is not evidence that the
        // packages are gone, and blanking the list would make a momentary
        // bridge hiccup look like data loss.
        setError({ message: "桌宠素材包读取失败", detail: errorMessage(reason, { includeDetail: true }) });
        setAnsweredRole(roleId);
      }
    })();
    return () => { alive = false; };
  }, [client, disabled, parse, roleId]);

  /** Runs one mutation, surfacing its failure instead of leaving the panel silent. */
  const run = useCallback(async (message: string, action: () => Promise<void>) => {
    setBusy(true);
    try {
      await action();
      setError(null);
    } catch (reason) {
      setError({ message, detail: errorMessage(reason, { includeDetail: true }) });
    } finally {
      setBusy(false);
    }
  }, []);

  const mutate = useCallback(async (method: "pets.import" | "pets.remove", payload: Record<string, unknown>) => {
    setState(parse(await client.call<unknown>(rpcMethods[method], { role_id: roleId, ...payload })));
    onRoleDataChanged();
    if (method !== "pets.import") await client.background.call("sync");
  }, [client, onRoleDataChanged, parse, roleId]);

  const onImport = useCallback((provider: PetPackageProvider) => void run("桌宠素材包导入未完成", async () => {
    const source = await pickPetPackageFile(pickFiles, provider.importOptions);
    if (source) await mutate("pets.import", { provider: provider.reference, source });
  }), [mutate, pickFiles, run]);

  /** Resolves once the removal has finished, failed or not (a failure lands in `error`). */
  const onRemove = useCallback((reference: PetModelReference) => run("桌宠素材包删除未完成", () => mutate("pets.remove", { ...reference })), [mutate, run]);
  const onSelect = useCallback((reference: PetModelReference) => void run("桌宠素材包切换未完成", async () => {
    // Prepare the candidate before committing a live role's selection.
    await client.background.call("select", { role_id: roleId, ...reference });
    setState(parse(await client.call<unknown>(rpcMethods["pets.list"], { role_id: roleId })));
    onRoleDataChanged();
  }), [client, onRoleDataChanged, parse, roleId, run]);

  return { state, loading: Boolean(roleId) && answeredRole !== roleId, busy, error, onImport, onRemove, onSelect };
}
