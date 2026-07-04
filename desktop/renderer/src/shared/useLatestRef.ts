import { useRef } from "react";

/** Keeps a mutable ref synchronized with the latest rendered value. */
export function useLatestRef<T>(value: T) {
  const ref = useRef(value);
  ref.current = value;
  return ref;
}
