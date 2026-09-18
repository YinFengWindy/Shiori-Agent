/** Build constants replaced by the fixture’s own esbuild invocation. */
declare const __FIXTURE_VERSION__: string;
declare const __RENDERER_FAILURE__: boolean;

/** Only the injected API used by this independently built example. */
export type FixtureClient = {
  call(name: string, payload?: Record<string, unknown>): Promise<Record<string, unknown>>;
  background: { call(name: string): Promise<Record<string, unknown>> };
  events: { on(name: string, handler: () => void): Promise<() => void> };
};

/** Narrow structural contract; no host source is needed to build the fixture. */
export type FixtureBackground = {
  rpc: { handle(name: string, callback: () => unknown): Promise<void> };
  events: FixtureClient["events"];
  store: { write(value: unknown): Promise<void> };
  effect(label: string, dispose: () => Promise<void>): void;
  surfaces: {
    create(id: string, spec: { body: { width: number; height: number }; transparent: boolean; alwaysOnTop: boolean; skipTaskbar: boolean }, anchor: { x: number; y: number }): Promise<unknown>;
    destroy(id: string): Promise<void>;
    show(id: string): void;
  };
};

declare global {
  const __FIXTURE_VERSION__: string;
  const __RENDERER_FAILURE__: boolean;
}
