import { useBridgeRefreshedValue } from "../shared/useBridgeRefreshedValue";

// Read when a phone screen opens; memory consolidation and listening
// settings push no event, so a screen shows what was stored when it opened.
const noRefreshEvents: ReadonlySet<string> = new Set();

/** A value read once per mount (or when `load` changes); `refresh` reads it again. */
export function usePhoneLoadedValue<T>(load: () => Promise<T>) {
  return useBridgeRefreshedValue({ load, refreshEvents: noRefreshEvents, refreshOnFocus: false });
}
