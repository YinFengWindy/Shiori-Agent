import { pathToFileURL } from "node:url";
import { localAssetScheme } from "./localAssetRegistry.js";

type NavigationEvent = {
  preventDefault(): void;
};

type WindowOpenDetails = {
  url: string;
};

type SecureWebContents = {
  on(event: "will-navigate", handler: (event: NavigationEvent, url: string) => void): void;
  setWindowOpenHandler(handler: (details: WindowOpenDetails) => { action: "deny" }): void;
};

type HeadersReceivedDetails = {
  resourceType?: string;
  responseHeaders?: Record<string, string[]>;
};

type HeadersReceivedResponse = {
  responseHeaders?: Record<string, string[]>;
};

type WebRequestAdapter = {
  onHeadersReceived(
    handler: (
      details: HeadersReceivedDetails,
      callback: (response: HeadersReceivedResponse) => void,
    ) => void,
  ): void;
};

/** Validates the optional Vite URL before Electron loads privileged preload code into it. */
export function validateRendererDevServerUrl(value: string | undefined): string | null {
  if (!value) {
    return null;
  }
  const requestedUrl = new URL(value);
  const trustedHost = requestedUrl.hostname === "127.0.0.1" || requestedUrl.hostname === "localhost";
  if (
    requestedUrl.protocol !== "http:"
    || !trustedHost
    || !requestedUrl.port
    || requestedUrl.username
    || requestedUrl.password
  ) {
    throw new Error(`Untrusted renderer development URL: ${value}`);
  }
  return requestedUrl.toString();
}

/** Returns the exact renderer entry URL accepted by the navigation policy. */
export function resolveRendererEntryUrl(
  rendererPath: string,
  devServerUrl: string | undefined,
): string {
  return validateRendererDevServerUrl(devServerUrl) ?? pathToFileURL(rendererPath).toString();
}

/** Builds the CSP applied to the privileged renderer main frame. */
export function buildDesktopContentSecurityPolicy(devServerUrl: string | undefined): string {
  const trustedDevUrl = validateRendererDevServerUrl(devServerUrl);
  const scriptSources = ["'self'"];
  const connectSources = ["'self'"];
  if (trustedDevUrl) {
    const url = new URL(trustedDevUrl);
    scriptSources.push("'unsafe-inline'");
    connectSources.push(`ws://${url.host}`);
  }
  return [
    "default-src 'self'",
    `script-src ${scriptSources.join(" ")}`,
    "style-src 'self' 'unsafe-inline'",
    `img-src 'self' data: blob: ${localAssetScheme}:`,
    `connect-src ${connectSources.join(" ")}`,
    "font-src 'self' data:",
    "object-src 'none'",
    "base-uri 'none'",
    "form-action 'none'",
    "frame-ancestors 'none'",
  ].join("; ");
}

/** Adds a CSP response header to renderer main-frame responses. */
export function registerDesktopContentSecurityPolicy(
  webRequest: WebRequestAdapter,
  devServerUrl: string | undefined,
): void {
  const policy = buildDesktopContentSecurityPolicy(devServerUrl);
  webRequest.onHeadersReceived((details, callback) => {
    if (details.resourceType !== "mainFrame") {
      callback({ responseHeaders: details.responseHeaders });
      return;
    }
    callback({
      responseHeaders: {
        ...details.responseHeaders,
        "Content-Security-Policy": [policy],
      },
    });
  });
}

/** Blocks renderer navigation and delegates authorized local attachment opens. */
export function attachDesktopWindowSecurity(
  webContents: SecureWebContents,
  options: {
    rendererEntryUrl: string;
    openLocalAttachment: (url: string) => Promise<unknown> | unknown;
  },
): void {
  const rendererEntry = new URL(options.rendererEntryUrl);
  webContents.on("will-navigate", (event, target) => {
    let requestedUrl: URL;
    try {
      requestedUrl = new URL(target);
    } catch {
      event.preventDefault();
      return;
    }
    const allowed = rendererEntry.protocol === "http:"
      ? requestedUrl.origin === rendererEntry.origin
      : requestedUrl.protocol === "file:" && requestedUrl.pathname === rendererEntry.pathname;
    if (!allowed) {
      event.preventDefault();
    }
  });
  webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith(`${localAssetScheme}:`)) {
      void Promise.resolve(options.openLocalAttachment(url));
    }
    return { action: "deny" };
  });
}
