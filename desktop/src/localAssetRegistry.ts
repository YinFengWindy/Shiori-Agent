import { randomUUID } from "node:crypto";
import { isAbsolute, resolve } from "node:path";
import {
  collectTrustedLocalAssetPaths,
  isLocalAssetInsideRoot,
  localAssetPathKey,
  resolveLocalAssetCandidate,
  type LocalAssetCandidate,
  type LocalAssetKind,
} from "./localAssetPolicy.js";
import type { LocalAssetReference } from "./shared.js";

export const localAssetScheme = "mira-asset";
export const maxLocalAssetBytes = 32 * 1024 * 1024;

/** Canonical local file authorization owned by the Electron main process. */
export type ResolvedLocalAsset = {
  token: string;
  requestedPath: string;
  canonicalPath: string;
  kind: LocalAssetKind;
  mimeType: string;
};

/** Tracks exact local files granted by trusted main-process or bridge boundaries. */
export class LocalAssetRegistry {
  private readonly grantsByToken = new Map<string, ResolvedLocalAsset>();
  private readonly tokensByPath = new Map<string, string>();
  private readonly trustedRoots = new Set<string>();

  addTrustedRoot(path: string): void {
    if (isAbsolute(path)) {
      this.trustedRoots.add(resolve(path));
    }
  }

  grantPath(path: string): LocalAssetReference | null {
    return this.grantManagedPath(path);
  }

  private grantCandidate(candidate: LocalAssetCandidate): LocalAssetReference {
    const existingToken = this.tokensByPath.get(localAssetPathKey(candidate.requestedPath));
    if (existingToken) {
      const existingGrant = this.grantsByToken.get(existingToken);
      if (
        existingGrant
        && localAssetPathKey(existingGrant.canonicalPath) === localAssetPathKey(candidate.canonicalPath)
      ) {
        return this.toReference(existingGrant);
      }
    }

    const grant: ResolvedLocalAsset = {
      token: randomUUID(),
      ...candidate,
    };
    this.grantsByToken.set(grant.token, grant);
    this.tokensByPath.set(localAssetPathKey(candidate.requestedPath), grant.token);
    this.tokensByPath.set(localAssetPathKey(candidate.canonicalPath), grant.token);
    return this.toReference(grant);
  }

  grantTrustedPayload(payload: unknown): LocalAssetReference[] {
    const references = new Map<string, LocalAssetReference>();
    for (const path of collectTrustedLocalAssetPaths(payload)) {
      const reference = this.grantManagedPath(path);
      if (reference) {
        references.set(reference.url, reference);
      }
    }
    return [...references.values()];
  }

  resolveReference(value: string): ResolvedLocalAsset | null {
    const cleanValue = value.trim();
    if (!cleanValue) {
      return null;
    }
    if (cleanValue.startsWith(`${localAssetScheme}:`)) {
      return this.resolveUrl(cleanValue);
    }
    if (!isAbsolute(cleanValue)) {
      return null;
    }
    const token = this.tokensByPath.get(localAssetPathKey(cleanValue));
    return token ? this.grantsByToken.get(token) ?? null : null;
  }

  resolveUrl(value: string): ResolvedLocalAsset | null {
    let requestedUrl: URL;
    try {
      requestedUrl = new URL(value);
    } catch {
      return null;
    }
    if (requestedUrl.protocol !== `${localAssetScheme}:` || requestedUrl.hostname !== "local") {
      return null;
    }
    if (requestedUrl.search || requestedUrl.hash) {
      return null;
    }
    const token = requestedUrl.pathname.replace(/^\/+/, "");
    if (!token || token.includes("/")) {
      return null;
    }
    return this.grantsByToken.get(token) ?? null;
  }

  pathsEqual(left: string, right: string): boolean {
    return localAssetPathKey(left) === localAssetPathKey(right);
  }

  private toReference(grant: ResolvedLocalAsset): LocalAssetReference {
    return {
      path: grant.requestedPath,
      url: `${localAssetScheme}://local/${grant.token}`,
      kind: grant.kind,
    };
  }

  private grantManagedPath(path: string): LocalAssetReference | null {
    const existingGrant = this.resolveReference(path);
    if (existingGrant) {
      return this.toReference(existingGrant);
    }
    const candidate = resolveLocalAssetCandidate(path);
    if (!candidate) {
      return null;
    }
    const insideTrustedRoot = [...this.trustedRoots].some((root) => (
      isLocalAssetInsideRoot(candidate.canonicalPath, root)
    ));
    return insideTrustedRoot ? this.grantCandidate(candidate) : null;
  }
}
