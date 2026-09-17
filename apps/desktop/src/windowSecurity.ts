import { pathToFileURL } from "node:url";
import { createHash } from "node:crypto";
import { pluginUiImportMap, pluginUiScheme } from "./plugins/uiContract.js";
import { localAssetScheme } from "./assets/localAssetContract.js";

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
  const scriptSources = ["'self'", `${pluginUiScheme}:`];
  const connectSources = ["'self'"];
  if (trustedDevUrl) {
    const url = new URL(trustedDevUrl);
    // 开发环境用 'unsafe-inline' 放行 Vite 注入的内联 preamble 脚本；
    // 按 CSP 规范，script-src 里只要出现 hash/nonce 来源，'unsafe-inline' 就会被整体忽略，
    // 所以这里绝不能再加导入映射的 sha256 hash，否则会复现 preamble 检测失败、白屏的回归。
    scriptSources.push("'unsafe-inline'");
    connectSources.push(`ws://${url.host}`);
  } else {
    // 打包环境没有内联 preamble 脚本，改用导入映射内容的 sha256 hash 精确放行，
    // 避免引入 'unsafe-inline' 扩大攻击面。
    const mapHash = createHash("sha256").update(pluginUiImportMap).digest("base64");
    scriptSources.push(`'sha256-${mapHash}'`);
  }
  return [
    "default-src 'self'",
    `script-src ${scriptSources.join(" ")}`,
    `style-src 'self' 'unsafe-inline' ${pluginUiScheme}:`,
    `img-src 'self' data: blob: ${localAssetScheme}: ${pluginUiScheme}:`,
    `connect-src ${connectSources.join(" ")}`,
    `font-src 'self' data: ${pluginUiScheme}:`,
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
