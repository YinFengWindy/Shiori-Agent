import { useEffect, useState } from "react";
import type { PluginRpcClient } from "../../../apps/desktop/renderer/src/plugins/pluginBridgeClient";

type ConnectionSettings = {
  ref: string;
  mode: "external" | "managed";
  ws_uri: string;
  timeout_seconds: number;
  has_token: boolean;
};

type Fields = { mode: "external" | "managed"; uri: string; token: string; timeout: string; clearToken: boolean };
const emptyFields: Fields = { mode: "external", uri: "", token: "", timeout: "5", clearToken: false };

type FormOptions = {
  accountId?: string;
  draftRef: string;
  client: PluginRpcClient;
  onChanged: (accountId?: string) => void;
};

/** Owns QQ connection form loading, a saved baseline, and explicit commands. */
export function useQQAccountForm({ accountId, draftRef, client, onChanged }: FormOptions) {
  const [fields, setFields] = useState<Fields>(emptyFields);
  const [saved, setSaved] = useState({ ref: "", mode: "external" as Fields["mode"], uri: "", timeout: "5", hasToken: false });
  const [managedAvailable, setManagedAvailable] = useState(false);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let current = true;
    setError("");
    if (!accountId && !draftRef) {
      setFields(emptyFields);
      setSaved({ ref: "", mode: "external", uri: "", timeout: "5", hasToken: false });
      void client.call<{ managed_available: boolean }>("accounts.settings")
        .then((result) => { if (current) setManagedAvailable(result.managed_available); })
        .catch((failure: unknown) => { if (current) setError(failure instanceof Error ? failure.message : String(failure)); });
      setLoading(false);
      return;
    }
    setLoading(true);
    void client.call<{ account: ConnectionSettings; managed_available: boolean }>("accounts.settings", accountId ? { account_id: accountId } : { ref: draftRef })
      .then(({ account: settings, managed_available: available }) => {
        if (!current) return;
        setManagedAvailable(available);
        const timeout = String(settings.timeout_seconds);
        const mode = settings.mode ?? "external";
        setFields({ mode, uri: settings.ws_uri, token: "", timeout, clearToken: false });
        setSaved({ ref: settings.ref, mode, uri: settings.ws_uri, timeout, hasToken: settings.has_token });
      })
      .catch((failure: unknown) => { if (current) setError(failure instanceof Error ? failure.message : String(failure)); })
      .finally(() => { if (current) setLoading(false); });
    return () => { current = false; };
  }, [accountId, draftRef, client]);

  const dirty = fields.mode !== saved.mode || (fields.mode === "external" && (fields.uri !== saved.uri || fields.timeout !== saved.timeout
    || Boolean(fields.token) || fields.clearToken));
  const ref = saved.ref || draftRef;
  const setField = <K extends keyof Fields>(key: K, value: Fields[K]) =>
    setFields((current) => ({ ...current, [key]: value }));

  async function run(operation: () => Promise<void>) {
    setBusy(true);
    setError("");
    try { await operation(); }
    catch (failure) { setError(failure instanceof Error ? failure.message : String(failure)); }
    finally { setBusy(false); }
  }

  const save = () => run(async () => {
    const uri = fields.uri.trim();
    const result = await client.call<{ ref: string }>("accounts.save", {
      account_id: accountId ?? "", ref, mode: fields.mode, ws_uri: uri, ws_token: fields.token,
      clear_token: fields.clearToken, timeout_seconds: Number(fields.timeout),
    });
    const hasToken = !fields.clearToken && (saved.hasToken || Boolean(fields.token));
    setFields({ mode: fields.mode, uri, token: "", timeout: fields.timeout, clearToken: false });
    setSaved({ ref: result.ref, mode: fields.mode, uri, timeout: fields.timeout, hasToken });
  });
  const connect = () => run(async () => {
    const result = await client.call<{ account_id: string }>("accounts.connect", { ref });
    if (result.account_id) onChanged(result.account_id);
  });
  const disconnect = () => run(async () => {
    if (accountId) await client.call("accounts.disconnect", { account_id: accountId });
    else if (fields.mode === "managed" && ref) await client.call("accounts.disconnect_draft", { ref });
    else return;
    onChanged();
  });

  return {
    fields, setField, hasToken: saved.hasToken, ref, dirty, busy, loading, error, managedAvailable, client,
    save, connect, disconnect,
  };
}
