/**
 * Picks the Windows installer out of a GitHub "latest release" API response,
 * so the download button can point straight at the file. Release assets are
 * versioned (`Shiori-Setup-<version>.exe`, desktop electron-builder
 * `artifactName`), so there is no fixed `/releases/latest/download/<name>`
 * URL to link at build time.
 */

/** The installer to link: its download URL and the release tag (e.g. `v0.5.2`), if the release has one. */
export interface InstallerLink {
  readonly url: string;
  readonly version: string | null;
}

const INSTALLER_NAME = /^Shiori-Setup-.+\.exe$/;
const DOWNLOAD_ORIGIN = "https://github.com/";

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

/**
 * The `Shiori-Setup-*.exe` asset of `release` (the parsed JSON of
 * `GET /repos/{owner}/{repo}/releases/latest`), or `null` when the response
 * has no such asset or is not shaped like a release. `.exe.blockmap` update
 * metadata never matches, and only GitHub-hosted download URLs are accepted.
 */
export function pickWindowsInstaller(release: unknown): InstallerLink | null {
  if (!isRecord(release) || !Array.isArray(release.assets)) return null;
  for (const asset of release.assets) {
    if (!isRecord(asset)) continue;
    const { name, browser_download_url: url } = asset;
    if (typeof name !== "string" || typeof url !== "string") continue;
    if (!INSTALLER_NAME.test(name) || !url.startsWith(DOWNLOAD_ORIGIN)) continue;
    return { url, version: typeof release.tag_name === "string" && release.tag_name ? release.tag_name : null };
  }
  return null;
}
