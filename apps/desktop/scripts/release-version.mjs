/** Resolves and validates the optional application version supplied by a release tag. */
export function resolveReleaseVersion(value = process.env.SHIORI_RELEASE_VERSION) {
  const version = value?.trim();
  if (!version) {
    return undefined;
  }
  if (!/^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$/.test(version)) {
    throw new Error(`Invalid release version: ${version}`);
  }
  return version;
}
