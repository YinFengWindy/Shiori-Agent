import { useCallback, useEffect, useState } from "react";
import { errorMessage, useLatestRef, type PluginRpcClient } from "@yinfengwindy/shiori-sdk";
import type { BilibiliAccountStatus, BilibiliLoginPoll, BilibiliLoginStart, BilibiliScanState } from "./liveContracts";
import { useSerialPoll } from "./useSerialPoll";

/** How often a shown QR asks Bilibili whether it was scanned. */
export const loginPollIntervalMs = 2000;

/** The QR being shown and how far its scan got. */
export type BilibiliQrLogin = { qrcode: string; scan: BilibiliScanState };

/**
 * The pet role's Bilibili login (#722): the stored account, and a QR login
 * shown in place. The QR is polled one request at a time while `open` and
 * until it is confirmed, expired, cancelled or fails; a late answer for a QR
 * no longer shown changes nothing.
 */
export function useBilibiliAccount(client: PluginRpcClient, roleId: string, open: boolean) {
  const [account, setAccount] = useState<BilibiliAccountStatus | null>(null);
  const [qr, setQr] = useState<BilibiliQrLogin | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  // Read after an awaited poll: is the QR it asked about still the one shown?
  const shownQr = useLatestRef(qr?.qrcode ?? null);

  const loadAccount = useCallback(async () => {
    setError("");
    try {
      setAccount(await client.call<BilibiliAccountStatus>("bilibili.account.status", { role_id: roleId }));
    } catch (cause) {
      setError(errorMessage(cause));
    }
  }, [client, roleId]);
  useEffect(() => { void loadAccount(); }, [loadAccount]);

  /** One user action at a time; its failure is shown and changes nothing else. */
  const run = async (action: () => Promise<void>) => {
    setBusy(true);
    setError("");
    try {
      await action();
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  };

  const poll = async () => {
    const asked = shownQr.current;
    try {
      const result = await client.call<BilibiliLoginPoll>("bilibili.login.poll", { role_id: roleId });
      if (shownQr.current !== asked) return;
      if (result.state === "success") {
        setQr(null);
        setAccount({ state: "logged_in", account: result.account });
      } else {
        setQr((current) => current && current.scan !== result.state ? { ...current, scan: result.state } : current);
      }
    } catch (cause) {
      if (shownQr.current !== asked) return;
      setQr(null);
      setError(errorMessage(cause));
    }
  };
  useSerialPoll(open && qr !== null && qr.scan !== "expired", loginPollIntervalMs, poll);

  return {
    account,
    qr,
    error,
    busy,
    /** Re-reads the account after a failed read. */
    reload: () => { void loadAccount(); },
    /** Shows a fresh QR, replacing any earlier one. */
    startLogin: () => run(async () => {
      const ticket = await client.call<BilibiliLoginStart>("bilibili.login.start", { role_id: roleId });
      setQr({ qrcode: ticket.qrcode, scan: ticket.state });
    }),
    /** Hides the QR; nothing is sent, the backend key simply expires. */
    cancelLogin: () => setQr(null),
    logout: () => run(async () => {
      setQr(null);
      setAccount(await client.call<BilibiliAccountStatus>("bilibili.account.logout", { role_id: roleId }));
    }),
  };
}

/** What the login panel reads from and acts through. */
export type BilibiliAccountController = ReturnType<typeof useBilibiliAccount>;
