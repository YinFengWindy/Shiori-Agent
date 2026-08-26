import { dirname, resolve } from "node:path";
import { tmpdir } from "node:os";
import { fileURLToPath } from "node:url";

const scriptsRoot = dirname(fileURLToPath(import.meta.url));
const desktopRoot = resolve(scriptsRoot, "..");
const repositoryRoot = resolve(desktopRoot, "..");

/** Resolves the release directories shared by runtime builds and packaging checks. */
export function resolveReleaseManifest({ releaseOutput = process.env.SHIORI_RELEASE_OUTPUT } = {}) {
  const releaseBuildRoot = resolve(repositoryRoot, "release");
  const installerOutput = releaseOutput
    ? resolve(releaseOutput)
    : resolve(process.env.LOCALAPPDATA ?? tmpdir(), "Shiori", "release");
  return {
    repositoryRoot,
    desktopRoot,
    releaseBuildRoot,
    runtimeOutput: resolve(releaseBuildRoot, "runtime"),
    pyinstallerWork: resolve(releaseBuildRoot, "pyinstaller-work"),
    installerOutput,
    unpackedOutput: resolve(installerOutput, "win-unpacked"),
  };
}

const invokedDirectly = process.argv[1] === fileURLToPath(import.meta.url);
if (invokedDirectly) {
  const manifest = resolveReleaseManifest();
  const field = process.argv[2];
  if (!field || !(field in manifest)) {
    throw new Error(`Unknown release manifest field: ${field ?? "<missing>"}`);
  }
  process.stdout.write(`${manifest[field]}\n`);
}
