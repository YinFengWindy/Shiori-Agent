import assert from "node:assert/strict";
import { copyFile, mkdir, readFile, rename, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { buildPlugin } from "../../../../scripts/build-plugin.mjs";

/** Build the existing neutral fixture through the public builder while its source stays in plugins/. */
export async function buildDistributionFixture(repository: string, source: string, output: string) {
  assert.equal(source, resolve(repository, "plugins/external_demo"));
  const fixture = resolve(repository, "tests/fixtures/external-plugin");
  const originalManifest = await readFile(resolve(fixture, "manifest.yaml"), "utf8");
  for (const version of ["1.0.0", "2.0.0", "3.0.0"]) {
    const manifest = originalManifest.replace(/^version: .+$/m, `version: '${version}'`) + "distribution: external\n";
    await writeFile(resolve(source, "manifest.yaml"), manifest, "utf8");
    for (const [input, destination] of [["plugin.py", "backend/plugin.py"], ["ui.tsx", "ui/index.tsx"], ["background.ts", "background/index.ts"], ["surface.tsx", "surface/index.tsx"]]) {
      const target = resolve(source, destination);
      await mkdir(dirname(target), { recursive: true });
      const text = (await readFile(resolve(fixture, "src", input), "utf8"))
        .replaceAll("__FIXTURE_VERSION__", input.endsWith(".py") ? version : JSON.stringify(version))
        .replaceAll("__RENDERER_FAILURE__", "false");
      await writeFile(target, text, "utf8");
      if (!input.endsWith(".py")) await copyFile(resolve(fixture, "src/contract.d.ts"), resolve(dirname(target), "contract.d.ts"));
    }
    await mkdir(resolve(source, "assets"), { recursive: true });
    await copyFile(resolve(fixture, "src/label.txt"), resolve(source, "assets/label.txt"));
    await copyFile(resolve(fixture, "src/style.css"), resolve(source, "style.css"));
    const built = await buildPlugin({ plugin: source, output });
    await rename(built.archive, resolve(output, `external_demo-${version}-valid.zip`));
  }
}
