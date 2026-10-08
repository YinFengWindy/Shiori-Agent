import { useCallback, useEffect, useRef, useState } from "react";
import { errorMessage, useLatestRef, type PluginRpcClient } from "@yinfengwindy/shiori-sdk";
import type { BilibiliAccountStatus, BilibiliLoginPoll, BilibiliLoginStart, BilibiliScanState } from "./liveContracts";
import { useSerialPoll } from "./useSerialPoll";

/** How often a shown QR asks Bilibili whether it was scanned. */
export const loginPollIntervalMs = 2000;

/** The QR being shown and how far its scan got. */
export type BilibiliQrLogin = { qrcode: string; scan: BilibiliScanState };

/**
 * The pet role's Bilibili login (#722): the stored account, re-checked each
 * time the dialog opens (an expired login shows as such), and a QR login
 * shown in place. The QR is polled one request at a time while `open` and
 * until it is confirmed, expired, cancelled or fails. A late scan progress or
 * error of a QR no longer shown changes nothing, but a late success still
 * applies: the backend has stored that login.
 */
export function useBilibiliAccount(client: PluginRpcClient, roleId: string, open: boolean) {
  const [account, setAccount] = useState<BilibiliAccountStatus | null>(null);
  const [qr, setQr] = useState<BilibiliQrLogin | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  // Read after an awaited poll: is the QR it asked about still the one shown?
  const shownQr = useLatestRef(qr?.qrcode ?? null);
  // Bumped by every account change (login, logout), so an older status read never undoes it.
  const accountChanges = useRef(0);

  const changeAccount = (next: BilibiliAccountStatus) => {
    accountChanges.current += 1;
    setAccount(next);
  };

  const loadAccount = useCallback(async () => {
    const since = accountChanges.current;
    setError("");
    try {
      const next = await client.call<BilibiliAccountStatus>("bilibili.account.status", { role_id: roleId });
      if (since === accountChanges.current) setAccount(next);
    } catch (cause) {
      setError(errorMessage(cause));
    }
  }, [client, roleId]);
  useEffect(() => { if (open) void loadAccount(); }, [open, loadAccount]);

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
      if (result.state === "success") {
        changeAccount({ state: "logged_in", account: result.account });
        setQr((current) => current?.qrcode === asked ? null : current);
      } else if (shownQr.current === asked) {
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
    /** Hides the QR; nothing is sent, the backend key simply expires. A poll already in flight may still log in. */
    cancelLogin: () => setQr(null),
    logout: () => run(async () => {
      setQr(null);
      // The backend drops the credentials and any pending QR and answers `{ state: "logged_out" }`.
      changeAccount(await client.call<BilibiliAccountStatus>("bilibili.account.logout", { role_id: roleId }));
    }),
  };
}

/** What the login panel reads from and acts through. */
export type BilibiliAccountController = ReturnType<typeof useBilibiliAccount>;
