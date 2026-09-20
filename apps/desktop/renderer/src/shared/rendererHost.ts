import { unavailableLocalAssetUrl } from "../../../src/bridge/shared";

/** Environment capabilities used by reusable views, without a complete DesktopApi. */
export type RendererHost = {
  localAssetUrl: (path: string) => string;
  openExternal: (url: string) => void;
};

const desktopHost: RendererHost = {
  localAssetUrl: (path) => typeof window !== "undefined" && window.miraDesktop
    ? window.miraDesktop.localAssetUrl(path) : unavailableLocalAssetUrl,
  openExternal: (url) => { void window.miraDesktop.openExternal(url); },
};

/** The composition root installs a host once before mounting reusable views. */
export let rendererHost = desktopHost;

/** Install explicit browser capabilities and return a teardown for isolated hosts/tests. */
export function installRendererHost(host: RendererHost) {
  const previous = rendererHost;
  rendererHost = host;
  return () => { rendererHost = previous; };
}
