import { useEffect, useState } from "react";
import type { PluginRpcClient } from "../../../apps/desktop/renderer/src/plugins/pluginBridgeClient";

type ConnectionSettings = {
  ref: string;
  ws_uri: string;
  timeout_seconds: number;
  has_token: boolean;
};

type Fields = { uri: string; token: string; timeout: string; clearToken: boolean };
const emptyFields: Fields = { uri: "", token: "", timeout: "5", clearToken: false };

type FormOptions = {
  accountId?: string;
  draftRef: string;
  client: PluginRpcClient;
  onChanged: (accountId?: string) => void;
};

/** Owns QQ connection form loading, a saved baseline, and explicit commands. */
export function useQQAccountForm({ accountId, draftRef, client, onChanged }: FormOptions) {
  const [fields, setFields] = useState<Fields>(emptyFields);
  const [saved, setSaved] = useState({ ref: "", uri: "", timeout: "5", hasToken: false });
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let current = true;
    setError("");
    if (!accountId && !draftRef) {
      setFields(emptyFields);
      setSaved({ ref: "", uri: "", timeout: "5", hasToken: false });
      setLoading(false);
      return;
    }
    setLoading(true);
    void client.call<{ account: ConnectionSettings }>("accounts.settings", accountId ? { account_id: accountId } : { ref: draftRef })
      .then(({ account: settings }) => {
        if (!current) return;
        const timeout = String(settings.timeout_seconds);
        setFields({ uri: settings.ws_uri, token: "", timeout, clearToken: false });
        setSaved({ ref: settings.ref, uri: settings.ws_uri, timeout, hasToken: settings.has_token });
      })
      .catch((failure: unknown) => { if (current) setError(failure instanceof Error ? failure.message : String(failure)); })
      .finally(() => { if (current) setLoading(false); });
    return () => { current = false; };
  }, [accountId, draftRef, client]);

  const dirty = fields.uri !== saved.uri || fields.timeout !== saved.timeout
    || Boolean(fields.token) || fields.clearToken;
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
      account_id: accountId ?? "", ref, ws_uri: uri, ws_token: fields.token,
      clear_token: fields.clearToken, timeout_seconds: Number(fields.timeout),
    });
    const hasToken = !fields.clearToken && (saved.hasToken || Boolean(fields.token));
    setFields({ uri, token: "", timeout: fields.timeout, clearToken: false });
    setSaved({ ref: result.ref, uri, timeout: fields.timeout, hasToken });
  });
  const connect = () => run(async () => {
    const result = await client.call<{ account_id: string }>("accounts.connect", { ref });
    onChanged(result.account_id);
  });
  const disconnect = () => run(async () => {
    if (!accountId) return;
    await client.call("accounts.disconnect", { account_id: accountId });
    onChanged();
  });

  return {
    fields, setField, hasToken: saved.hasToken, ref, dirty, busy, loading, error,
    save, connect, disconnect,
  };
}
