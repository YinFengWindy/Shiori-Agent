/**
 * Development-only test support for plugin renderer code
 * (`@shiori/plugin-sdk/testing`). Not a runtime peer: it is never part of the
 * renderer import map, so production plugin code must not import it.
 */

/** A promise the test settles on demand, for holding a response until state has changed. */
export function deferred<T>() {
  let resolve: (value: T) => void = () => undefined;
  let reject: (error: unknown) => void = () => undefined;
  const promise = new Promise<T>((onResolve, onReject) => { resolve = onResolve; reject = onReject; });
  return { promise, resolve, reject };
}
