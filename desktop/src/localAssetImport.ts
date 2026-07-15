import { createHash, randomUUID } from "node:crypto";
import { mkdir, readFile, rename, rm, stat, writeFile } from "node:fs/promises";
import { basename, join } from "node:path";
import { maxLocalAssetBytes } from "./localAssetRegistry.js";
import { resolveLocalAssetCandidate } from "./localAssetPolicy.js";

function contentDigest(data: Uint8Array): string {
  return createHash("sha256").update(data).digest("hex");
}

async function existingImportMatches(path: string, expectedDigest: string): Promise<boolean> {
  try {
    const data = await readFile(path);
    return contentDigest(data) === expectedDigest;
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") {
      return false;
    }
    throw error;
  }
}

/** Copies supported picker files into a private content-addressed import directory. */
export async function importLocalAssets(
  sourcePaths: string[],
  importsRoot: string,
): Promise<string[]> {
  await mkdir(importsRoot, { recursive: true });
  const importedPaths: string[] = [];
  for (const sourcePath of sourcePaths) {
    const candidate = resolveLocalAssetCandidate(sourcePath);
    if (!candidate) {
      throw new Error(`unsupported local asset: ${sourcePath}`);
    }
    const sourceStats = await stat(candidate.canonicalPath);
    if (sourceStats.size > maxLocalAssetBytes) {
      throw new Error(`local asset exceeds size limit: ${sourcePath}`);
    }
    const data = await readFile(candidate.canonicalPath);
    if (data.byteLength > maxLocalAssetBytes) {
      throw new Error(`local asset exceeds size limit: ${sourcePath}`);
    }
    const digest = contentDigest(data);
    const destinationDirectory = join(importsRoot, digest);
    await mkdir(destinationDirectory, { recursive: true });
    const destinationPath = join(destinationDirectory, basename(candidate.requestedPath));
    if (await existingImportMatches(destinationPath, digest)) {
      importedPaths.push(destinationPath);
      continue;
    }
    const temporaryPath = join(destinationDirectory, `.${randomUUID()}.tmp`);
    try {
      await writeFile(temporaryPath, data, { flag: "wx" });
      try {
        await rename(temporaryPath, destinationPath);
      } catch (error) {
        const code = (error as NodeJS.ErrnoException).code;
        if (!["EEXIST", "EPERM"].includes(code ?? "")
          || !await existingImportMatches(destinationPath, digest)) {
          throw error;
        }
      }
    } finally {
      await rm(temporaryPath, { force: true });
    }
    importedPaths.push(destinationPath);
  }
  return importedPaths;
}
