import { access, stat } from "node:fs/promises";
import { constants } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { resolveReleaseOutputDirectory } from "./release-paths.mjs";

async function requireFile(path) {
  await access(path, constants.R_OK);
  const details = await stat(path);
  if (!details.isFile()) {
    throw new Error(`Expected packaged file at ${path}`);
  }
}

async function requireDirectory(path) {
  await access(path, constants.R_OK);
  const details = await stat(path);
  if (!details.isDirectory()) {
    throw new Error(`Expected packaged directory at ${path}`);
  }
}

export async function verifyPackagedDesktop(appOutDir) {
  const resources = join(appOutDir, "resources");
  await Promise.all([
    requireFile(join(resources, "app.asar")),
    requireFile(join(resources, "runtime", "shiori-runtime.exe")),
    requireFile(join(resources, "config.example.toml")),
    requireFile(join(resources, "assets", "shiori-app-icon.ico")),
    requireDirectory(join(resources, "app.asar.unpacked", "node_modules", "uiohook-napi")),
  ]);
}

export default async function afterPack(context) {
  await verifyPackagedDesktop(context.appOutDir);
}

const invokedDirectly = process.argv[1] === fileURLToPath(import.meta.url);
if (invokedDirectly) {
  const here = dirname(fileURLToPath(import.meta.url));
  const appOutDir = process.argv[2]
    ? resolve(process.argv[2])
    : resolve(resolveReleaseOutputDirectory(), "win-unpacked");
  await verifyPackagedDesktop(appOutDir);
}
