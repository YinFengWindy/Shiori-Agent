import { readFile, realpath, stat } from "node:fs/promises";
import { extname, relative, resolve } from "node:path";
import { PluginResourceRegistry, pluginResourceScheme } from "./resourceRegistry.js";

export const maxPluginResourceBytes = 32 * 1024 * 1024;
export const pluginResourceSchemePrivileges = Object.freeze({
  standard: true,
  secure: true,
  supportFetchAPI: true,
});

const MIME_TYPES: Readonly<Record<string, string>> = Object.freeze({
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".mjs": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".gif": "image/gif",
  ".webp": "image/webp",
  ".woff": "font/woff",
  ".woff2": "font/woff2",
  ".mp3": "audio/mpeg",
  ".wav": "audio/wav",
});

const PLUGIN_CSP = [
  "default-src 'self'",
  "script-src 'self'",
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob:",
  "media-src 'self' data: blob:",
  "font-src 'self' data:",
  "connect-src 'none'",
  "object-src 'none'",
  "base-uri 'none'",
  "form-action 'none'",
  "frame-ancestors 'none'",
].join("; ");

type ProtocolRegistrar = {
  handle(scheme: string, handler: (request: { url: string }) => Promise<Response> | Response): void;
};

function errorResponse(message: string, status: number): Response {
  return new Response(message, {
    status,
    headers: { "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff" },
  });
}

/** Serves one file contained by an installed plugin package root. */
export async function loadPluginResource(
  registry: PluginResourceRegistry,
  requestUrl: string,
): Promise<Response> {
  let url: URL;
  try {
    url = new URL(requestUrl);
  } catch {
    return errorResponse("invalid plugin resource URL", 400);
  }
  if (url.protocol !== `${pluginResourceScheme}:` || url.search || url.hash) {
    return errorResponse("invalid plugin resource URL", 400);
  }
  const packageRoot = registry.packageRoot(url.hostname);
  if (!packageRoot) return errorResponse("plugin package is not registered", 403);
  let requestedPath: string;
  try {
    requestedPath = decodeURIComponent(url.pathname.replace(/^\/+/, ""));
  } catch {
    return errorResponse("invalid plugin resource path", 400);
  }
  if (!requestedPath || requestedPath.includes("\\") || requestedPath.split("/").includes("..")) {
    return errorResponse("invalid plugin resource path", 400);
  }
  const mimeType = MIME_TYPES[extname(requestedPath).toLowerCase()];
  if (!mimeType) return errorResponse("plugin resource type is not allowed", 415);
  try {
    const canonicalRoot = await realpath(packageRoot);
    const canonicalTarget = await realpath(resolve(canonicalRoot, requestedPath));
    const containment = relative(canonicalRoot, canonicalTarget);
    if (!containment || containment.startsWith("..") || resolve(canonicalRoot, containment) !== canonicalTarget) {
      return errorResponse("plugin resource escapes package root", 403);
    }
    const fileStats = await stat(canonicalTarget);
    if (!fileStats.isFile()) return errorResponse("plugin resource is not a file", 403);
    if (fileStats.size > maxPluginResourceBytes) return errorResponse("plugin resource exceeds size limit", 413);
    const body = await readFile(canonicalTarget);
    return new Response(body, {
      status: 200,
      headers: {
        "Cache-Control": "no-store",
        "Content-Length": String(body.byteLength),
        "Content-Security-Policy": PLUGIN_CSP,
        "Content-Type": mimeType,
        "X-Content-Type-Options": "nosniff",
      },
    });
  } catch (error) {
    const code = (error as NodeJS.ErrnoException).code;
    if (code === "ENOENT") return errorResponse("plugin resource was not found", 404);
    if (code === "EACCES" || code === "EPERM") return errorResponse("plugin resource access was denied", 403);
    return errorResponse("plugin resource could not be loaded", 500);
  }
}

/** Registers the isolated plugin resource protocol. */
export function registerPluginResourceProtocol(
  protocol: ProtocolRegistrar,
  registry: PluginResourceRegistry,
): void {
  protocol.handle(pluginResourceScheme, (request) => loadPluginResource(registry, request.url));
}
