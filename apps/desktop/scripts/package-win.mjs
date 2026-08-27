import { spawn } from "node:child_process";
import { resolve } from "node:path";
import { resolveReleaseManifest } from "./release-manifest.mjs";
import { resolveReleaseVersion } from "./release-version.mjs";

const releaseManifest = resolveReleaseManifest();
const builderCli = resolve(releaseManifest.desktopRoot, "node_modules", "electron-builder", "cli.js");
const outputDirectory = releaseManifest.installerOutput;
const releaseVersion = resolveReleaseVersion();
const versionArgs = releaseVersion ? [`--config.extraMetadata.version=${releaseVersion}`] : [];
const child = spawn(process.execPath, [
  builderCli,
  "--projectDir",
  releaseManifest.desktopRoot,
  `--config.directories.output=${outputDirectory}`,
  ...versionArgs,
  "--win",
  "--x64",
  "--publish",
  "never",
], {
  cwd: releaseManifest.desktopRoot,
  stdio: "inherit",
});

child.once("error", (error) => {
  throw error;
});
const exitCode = await new Promise((resolveExit) => child.once("exit", (code) => resolveExit(code ?? 1)));
process.exitCode = exitCode;
