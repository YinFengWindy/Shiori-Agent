import { useCallback, useEffect, useRef, useState } from "react";
import { createIdentityClient, type UserIdentity } from "./identityClient";
import { identityBindingKeys } from "./identityPresentation";

const client = createIdentityClient();

/**
 * Keeps the bound identities current: loads on mount and reloads whenever the
 * host pushes `identities.updated` (bind, unbind, or a newly known chat).
 * `onBound` runs when a reload brings a binding the previous load did not
 * have — i.e. a pairing code was just used. It must be a stable callback.
 */
export function useIdentities(onBound: () => void) {
  const [identities, setIdentities] = useState<UserIdentity[] | null>(null);
  const [error, setError] = useState("");
  const request = useRef(0);
  // Binding keys of the last successful load; null until the first one.
  const known = useRef<Set<string> | null>(null);
  const reload = useCallback(async () => {
    const current = ++request.current;
    try {
      const next = await client.list();
      if (current !== request.current) return;
      const keys = identityBindingKeys(next);
      const previous = known.current;
      known.current = keys;
      setIdentities(next);
      setError("");
      if (previous && [...keys].some((key) => !previous.has(key))) onBound();
    } catch (failure) {
      if (current === request.current) setError(failure instanceof Error ? failure.message : String(failure));
    }
  }, [onBound]);
  useEffect(() => { void reload(); }, [reload]);
  useEffect(() => window.miraDesktop.onEvent((event) => {
    if (event.method === "identities.updated") void reload();
  }), [reload]);
  return { identities, error, reload };
}
