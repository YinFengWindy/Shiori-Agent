import { useLayoutEffect, useRef } from "react";

/** Keeps a mutable ref synchronized with the latest rendered value. */
export function useLatestRef<T>(value: T) {
  const ref = useRef(value);
  useLayoutEffect(() => {
    ref.current = value;
  }, [value]);
  return ref;
}
