import { tmpdir } from "node:os";
import { resolve } from "node:path";

export function resolveReleaseOutputDirectory() {
  if (process.env.SHIORI_RELEASE_OUTPUT) {
    return resolve(process.env.SHIORI_RELEASE_OUTPUT);
  }
  return resolve(process.env.LOCALAPPDATA ?? tmpdir(), "Shiori", "release");
}
