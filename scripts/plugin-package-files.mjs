import { copyFile, lstat, mkdir, readdir, realpath } from "node:fs/promises";
import { dirname, join, resolve } from "node:path";

const omitted = new Set(["tests", "__pycache__", "node_modules", "venv", "env", "build", "dist", "artifacts"]);

/** Require portable relative paths, including when called with manifest asset paths. */
export function packageFile(root, name) {
  if (typeof name !== "string" || !name || name.includes("\\") || name.includes(":")) throw new Error(`Invalid package path: ${name}`);
  const parts = name.split("/");
  if (parts.some((part) => !part || part === "." || part === ".." || /[\x00-\x1f]/.test(part))) throw new Error(`Invalid package path: ${name}`);
  return join(root, ...parts);
}

/** Skip source-only environments, tests, caches and bytecode in every copied subtree. */
export function distributablePath(name) {
  return !name.split("/").some((part) => part.startsWith(".") || omitted.has(part)) && !/\.py[co]$/i.test(name);
}

/** Copy only regular, contained package files; never follow source symlinks/junctions. */
export async function copyPackagePath(source, destination, name) {
  if (!distributablePath(name)) throw new Error(`Development-only path cannot be packaged: ${name}`);
  const input = packageFile(source, name);
  const info = await lstat(input);
  if (info.isSymbolicLink() || await realpath(input) !== resolve(input)) throw new Error(`Package links are unsupported: ${name}`);
  if (info.isDirectory()) {
    for (const entry of await readdir(input)) {
      const child = `${name}/${entry}`;
      if (distributablePath(child)) await copyPackagePath(source, destination, child);
    }
  } else if (info.isFile()) {
    const output = packageFile(destination, name);
    await mkdir(dirname(output), { recursive: true });
    await copyFile(input, output);
  } else throw new Error(`Not a regular package file: ${name}`);
}

/** Select backend, explicit assets and documentation without copying the development tree. */
export async function copyPluginSources(source, destination, manifest) {
  await copyPackagePath(source, destination, "backend");
  for (const asset of manifest.assets ?? []) await copyPackagePath(source, destination, asset);
  for (const name of await readdir(source)) {
    if (name === "docs" || /^(?:README|LICENSE|NOTICE|COPYING)(?:[._-].*)?$/i.test(name)) {
      await copyPackagePath(source, destination, name);
    }
  }
}
