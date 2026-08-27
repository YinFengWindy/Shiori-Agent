import type { DesktopApi } from "../../src/bridge/shared";

declare global {
  interface Window {
    miraDesktop: DesktopApi;
  }
}

export {};
