/** Minimal persisted-state port used by the static demo and its isolated tests. */
export type DemoStorage = Pick<Storage, "getItem" | "setItem" | "removeItem">;

/** Read only a versioned sample; malformed browser storage starts a fresh demo. */
export function readDemoStorage<T>(storage: DemoStorage, key: string, validate: (value: unknown) => value is T): T | null {
  const raw = storage.getItem(key);
  if (!raw) return null;
  try {
    const value: unknown = JSON.parse(raw);
    return validate(value) ? value : null;
  } catch {
    return null;
  }
}
