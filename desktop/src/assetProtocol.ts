import { readFile, realpath, stat } from "node:fs/promises";
import {
  LocalAssetRegistry,
  localAssetScheme,
  maxLocalAssetBytes,
} from "./localAssetRegistry.js";

export const localAssetSchemePrivileges = Object.freeze({
  standard: true,
  secure: true,
});

type ProtocolRegistrar = {
  handle(
    scheme: string,
    handler: (request: { url: string }) => Promise<Response> | Response,
  ): void;
};

function errorResponse(message: string, status: number): Response {
  return new Response(message, {
    status,
    headers: {
      "Cache-Control": "no-store",
      "X-Content-Type-Options": "nosniff",
    },
  });
}

/** Reads one previously authorized image and returns a stable protocol response. */
export async function loadGrantedLocalAsset(
  registry: LocalAssetRegistry,
  requestUrl: string,
): Promise<Response> {
  const grant = registry.resolveUrl(requestUrl);
  if (!grant) {
    return errorResponse("asset is not authorized", 403);
  }
  if (grant.kind !== "image") {
    return errorResponse("asset type cannot be rendered", 415);
  }

  try {
    const currentRealPath = await realpath(grant.requestedPath);
    if (!registry.pathsEqual(currentRealPath, grant.canonicalPath)) {
      return errorResponse("asset authorization is stale", 403);
    }
    const fileStats = await stat(currentRealPath);
    if (!fileStats.isFile()) {
      return errorResponse("asset is not a regular file", 403);
    }
    if (fileStats.size > maxLocalAssetBytes) {
      return errorResponse("asset exceeds size limit", 413);
    }
    const data = await readFile(currentRealPath);
    return new Response(data, {
      status: 200,
      headers: {
        "Cache-Control": "no-store",
        "Content-Length": String(data.byteLength),
        "Content-Type": grant.mimeType,
        "X-Content-Type-Options": "nosniff",
      },
    });
  } catch (error) {
    const code = (error as NodeJS.ErrnoException).code;
    if (code === "ENOENT") {
      return errorResponse("asset was not found", 404);
    }
    if (code === "EACCES" || code === "EPERM") {
      return errorResponse("asset access was denied", 403);
    }
    return errorResponse("asset could not be loaded", 500);
  }
}

/** Registers the local image protocol against an injected Electron protocol adapter. */
export function registerLocalAssetProtocol(
  protocol: ProtocolRegistrar,
  registry: LocalAssetRegistry,
): void {
  protocol.handle(localAssetScheme, async (request) => (
    await loadGrantedLocalAsset(registry, request.url)
  ));
}
