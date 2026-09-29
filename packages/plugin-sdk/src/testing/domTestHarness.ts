/*
 * DOM test harness of the SDK's testing entry (#505), shared by host and
 * plugin tests. Each mount installs a fresh happy-dom window as the global
 * DOM. Base UI (under the SDK's `Select` and `ActionMenu`) decides at module
 * load whether a DOM exists; the desktop unit test loader
 * (`apps/desktop/scripts/test-unit-loader.mjs`) settles that answer before any
 * test file loads, so components mounted here behave as in a browser.
 */
import { Window } from "happy-dom";
import { act, type ReactNode } from "react";

/** Options of `mountTestComponent`. */
export type MountTestComponentOptions = {
  /**
   * Extra properties installed on the test window before the component mounts.
   *
   * Needed because this harness replaces `globalThis.window` with a fresh
   * happy-dom window that has nothing else on it. Anything reading a window
   * global from an effect (in host tests, the desktop preload bridge
   * `window.miraDesktop`) would otherwise throw on mount, and there is no
   * point after `mountTestComponent` returns at which a test could still
   * install it, because React has already flushed its effects.
   */
  windowGlobals?: Record<string, unknown>;
};

/**
 * `windowGlobals` that route the test window's timers through Node's global
 * `setTimeout` / `clearTimeout`, so `context.mock.timers` controls them.
 *
 * happy-dom binds its window timers to the real Node timers when its module
 * loads, so a component's `window.setTimeout` never sees `mock.timers` on its
 * own. The global is looked up on every call, so the mock only has to be
 * enabled before the component schedules its timer.
 *
 * Only `setTimeout` / `setInterval` with `(handler, delay)` and their
 * `clear*` counterparts are forwarded — no extra callback arguments — which
 * is all the current callers use; extend it when a component needs more.
 */
export const mockableWindowTimers = {
  setTimeout: (handler: () => void, delay?: number) => globalThis.setTimeout(handler, delay),
  clearTimeout: (id: Parameters<typeof globalThis.clearTimeout>[0]) => globalThis.clearTimeout(id),
  setInterval: (handler: () => void, delay?: number) => globalThis.setInterval(handler, delay),
  clearInterval: (id: Parameters<typeof globalThis.clearInterval>[0]) => globalThis.clearInterval(id),
};

/** Mounts a React component with DOM events and restores browser globals after cleanup. */
export async function mountTestComponent(component: ReactNode, options: MountTestComponentOptions = {}) {
  const browserWindow = new Window();
  for (const [name, value] of Object.entries(options.windowGlobals ?? {})) {
    Object.defineProperty(browserWindow, name, { configurable: true, writable: true, value });
  }
  const globals = {
    window: browserWindow,
    document: browserWindow.document,
    navigator: browserWindow.navigator,
    HTMLElement: browserWindow.HTMLElement,
    Element: browserWindow.Element,
    Node: browserWindow.Node,
    ShadowRoot: browserWindow.ShadowRoot,
    MutationObserver: browserWindow.MutationObserver,
    ResizeObserver: browserWindow.ResizeObserver,
    getComputedStyle: browserWindow.getComputedStyle.bind(browserWindow),
    requestAnimationFrame: browserWindow.requestAnimationFrame.bind(browserWindow),
    cancelAnimationFrame: browserWindow.cancelAnimationFrame.bind(browserWindow),
    HTMLInputElement: browserWindow.HTMLInputElement,
    Event: browserWindow.Event,
    MouseEvent: browserWindow.MouseEvent,
    PointerEvent: browserWindow.PointerEvent,
    KeyboardEvent: browserWindow.KeyboardEvent,
    FocusEvent: browserWindow.FocusEvent,
    IS_REACT_ACT_ENVIRONMENT: true,
  };
  const originalGlobals = new Map<string, PropertyDescriptor | undefined>();
  for (const [name, value] of Object.entries(globals)) {
    originalGlobals.set(name, Object.getOwnPropertyDescriptor(globalThis, name));
    Object.defineProperty(globalThis, name, { configurable: true, writable: true, value });
  }
  const { createRoot } = await import("react-dom/client");
  const container = document.createElement("div");
  document.body.append(container);
  const root = createRoot(container);
  await act(async () => root.render(component));

  return {
    container,
    /** The happy-dom window, for tests that must patch layout the DOM does not implement. */
    window: browserWindow,
    async render(next: ReactNode) {
      await act(async () => root.render(next));
    },
    async cleanup() {
      await act(async () => root.unmount());
      await browserWindow.happyDOM.close();
      for (const [name, descriptor] of originalGlobals) {
        if (descriptor) Object.defineProperty(globalThis, name, descriptor);
        else Reflect.deleteProperty(globalThis, name);
      }
    },
  };
}

/** Dispatches a native input event after bypassing React's programmatic value tracker. */
export async function changeInputValue(input: HTMLInputElement | HTMLTextAreaElement, value: string) {
  const setValue = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(input), "value")?.set;
  if (!setValue) throw new Error("Input value setter is unavailable");
  await act(async () => {
    setValue.call(input, value);
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
}
