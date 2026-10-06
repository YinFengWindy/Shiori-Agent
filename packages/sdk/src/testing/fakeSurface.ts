import type { SurfaceHandle } from "../contract/surface";

/** Create a complete injected surface; override only the interactions a test exercises. */
export function createFakeSurfaceHandle(overrides: Partial<SurfaceHandle> = {}): SurfaceHandle {
  return {
    beginDrag() {},
    endDrag() {},
    setExtension() {},
    setClickThrough() {},
    onPlacement: () => () => {},
    onMessage: () => () => {},
    onState: () => () => {},
    onRoleActivity: () => () => {},
    postToBackground() {},
    ready() {},
    showContextMenu: async () => null,
    activateMainWindow() {},
    ...overrides,
  };
}
