import { localAssetAuthority, localAssetScheme, unavailableLocalAssetUrl } from "./localAssetContract.js";
import type { LocalAssetTransport } from "../bridge/shared.js";

export { unavailableLocalAssetUrl } from "./localAssetContract.js";

const opaqueLocalAssetUrlPattern = new RegExp(`^${localAssetScheme}://${localAssetAuthority}/[^/?#]+$`);

/** Stores opaque local asset URLs received from trusted main-process transports. */
export class PreloadLocalAssetCache {
  private readonly urlsByPath = new Map<string, string>();

  /** Caches the transport's asset references and returns its renderer-facing value. */
  consume<T>(transport: LocalAssetTransport<T>): T {
    for (const asset of transport.assets) {
      if (opaqueLocalAssetUrlPattern.test(asset.url)) {
        this.urlsByPath.set(asset.path, asset.url);
      }
    }
    return transport.value;
  }

  /** Returns an opaque URL without exposing unknown local paths. */
  resolve(path: string): string {
    return this.urlsByPath.get(path) ?? unavailableLocalAssetUrl;
  }
}
