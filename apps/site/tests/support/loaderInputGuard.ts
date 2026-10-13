import { runInNewContext } from "node:vm";

/** A fake input event for the loader's guard: what it was, and what the guard did to it. */
export interface GuardedEvent {
  type: string;
  key?: string;
  /** Whether the event's target sits inside a `[data-loader-passthrough]` control. */
  onPassthrough: boolean;
}

/** What the loader's input guard did to one event. */
export interface GuardOutcome {
  prevented: boolean;
  stopped: boolean;
}

/**
 * Runs the home page loader's inline script (SiteLoader.astro) as a browser
 * would on a plain visit, in a context holding stand-ins for the globals it
 * reads, and returns a function feeding one input event through the
 * window-level guard it installs while the loader shows (#806). The
 * pictures never finish loading here, so the loader stays up.
 */
export function runLoaderInputGuard(script: string): (event: GuardedEvent) => GuardOutcome {
  const listeners = new Map<string, (event: unknown) => void>();
  const element = {
    dataset: {} as Record<string, string>,
    style: { setProperty: () => undefined },
    setAttribute: () => undefined,
    addEventListener: () => undefined,
    querySelector: () => null,
    remove: () => undefined,
  };
  class FakeElement {
    constructor(private readonly onPassthrough: boolean) {}
    closest(selector: string) {
      return selector === "[data-loader-passthrough]" && this.onPassthrough ? this : null;
    }
  }
  runInNewContext(script, {
    Element: FakeElement,
    document: {
      getElementById: (id: string) => (id === "site-loader" ? element : null),
      documentElement: { hasAttribute: () => false, dataset: {} },
      readyState: "loading",
      addEventListener: () => undefined,
      querySelectorAll: () => [],
    },
    window: {
      addEventListener: (type: string, listener: (event: unknown) => void) => listeners.set(type, listener),
      removeEventListener: () => undefined,
    },
    getComputedStyle: () => ({ getPropertyValue: () => "10s" }),
    performance: { now: () => 0 },
    setTimeout: () => 0,
    JSON,
  });
  return ({ type, key, onPassthrough }) => {
    const listener = listeners.get(type);
    if (!listener) throw new Error(`the loader guards no ${type} events`);
    const outcome = { prevented: false, stopped: false };
    listener({
      type,
      key,
      cancelable: true,
      target: new FakeElement(onPassthrough),
      preventDefault: () => {
        outcome.prevented = true;
      },
      stopImmediatePropagation: () => {
        outcome.stopped = true;
      },
    });
    return outcome;
  };
}
