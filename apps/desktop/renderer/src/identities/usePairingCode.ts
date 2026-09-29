import { useCallback, useEffect, useState } from "react";
import { parseTimestamp } from "../shared/format";
import { errorMessage } from "@shiori/plugin-sdk";
import { createIdentityClient } from "./identityClient";

const client = createIdentityClient();

/** Countdown refresh period; the display has whole-second precision. */
const tickMs = 1000;

type ShownCode = { code: string; expiresAtMs: number };

/**
 * The pairing code currently on screen and its live countdown. Creating a
 * new code replaces the shown one; the code disappears once it expires or
 * when `clear` is called (it was consumed by a binding).
 */
export function usePairingCode() {
  const [shown, setShown] = useState<ShownCode | null>(null);
  const [now, setNow] = useState(() => Date.now());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    if (!shown) return undefined;
    const timer = window.setInterval(() => {
      const current = Date.now();
      // Expired codes match nothing on the host, so stop showing them.
      if (current >= shown.expiresAtMs) setShown(null);
      else setNow(current);
    }, tickMs);
    return () => window.clearInterval(timer);
  }, [shown]);
  const create = useCallback(async () => {
    setBusy(true);
    setError("");
    try {
      const next = await client.createPairingCode();
      const expiresAt = parseTimestamp(next.expiresAt);
      if (!expiresAt) throw new Error(`配对码过期时间无效：${next.expiresAt}`);
      setNow(Date.now());
      setShown({ code: next.code, expiresAtMs: expiresAt.getTime() });
    } catch (failure) {
      setError(errorMessage(failure));
    } finally {
      setBusy(false);
    }
  }, []);
  const clear = useCallback(() => setShown(null), []);
  return {
    code: shown?.code ?? null,
    remainingMs: shown ? shown.expiresAtMs - now : 0,
    busy, error, create, clear,
  };
}
