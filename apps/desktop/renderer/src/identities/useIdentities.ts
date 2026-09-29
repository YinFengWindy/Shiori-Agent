import { useRef } from "react";
import type { BridgeEvent } from "../../../src/bridge/shared";
import { useBridgeRefreshedValue } from "../shared/useBridgeRefreshedValue";
import { createIdentityClient, type UserIdentity } from "./identityClient";
import { identityBindingKeys } from "./identityPresentation";

const client = createIdentityClient();
const loadIdentities = () => client.list();

/** The host pushes `identities.updated` on bind, unbind, or a newly known chat. */
function identitiesMayHaveChanged(event: BridgeEvent) {
  return event.method === "identities.updated";
}

/**
 * Keeps the bound identities current: loads on mount and reloads whenever the
 * host pushes `identities.updated`. `onBound` runs when a reload brings a
 * binding the previous load did not have — i.e. a pairing code was just used.
 */
export function useIdentities(onBound: () => void) {
  // Binding keys of the last successful load; null until the first one.
  const previousBindingKeys = useRef<Set<string> | null>(null);
  function detectNewBinding(loaded: UserIdentity[]) {
    const keys = identityBindingKeys(loaded);
    const previous = previousBindingKeys.current;
    previousBindingKeys.current = keys;
    if (previous && [...keys].some((key) => !previous.has(key))) onBound();
  }
  const { value: identities, error, refresh: reload } = useBridgeRefreshedValue({
    load: loadIdentities, refreshEvents: identitiesMayHaveChanged, onLoaded: detectNewBinding,
    refreshOnFocus: false, keepValueOnError: true,
  });
  return { identities, error, reload };
}
