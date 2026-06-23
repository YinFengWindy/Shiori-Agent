import type { DesktopApi } from "../../src/shared";

declare global {
  interface Window {
    miraDesktop: DesktopApi;
  }
}

export {};
