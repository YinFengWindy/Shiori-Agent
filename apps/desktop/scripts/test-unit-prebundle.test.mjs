import assert from "node:assert/strict";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import { pathToFileURL } from "node:url";
import { prebundleTestDependencies } from "./test-unit-prebundle.mjs";

// The redirect only fires when its key is exactly the URL Node resolves the
// import to; if the two drift apart, tests still pass but every process loads
// the unbundled graph again and the suite silently slows back down.
test("the redirect table is keyed by the entry files Node resolves", async () => {
  const outDir = await mkdtemp(join(tmpdir(), "shiori-desktop-prebundle-test-"));
  try {
    const redirects = JSON.parse(await readFile(await prebundleTestDependencies(outDir), "utf8"));
    for (const specifier of ["@base-ui/react/select", "@base-ui/react/menu", "@base-ui/react/dialog", "happy-dom"]) {
      const bundled = redirects[import.meta.resolve(specifier)];
      assert.ok(bundled, `no prebundle redirect for ${specifier}`);
      assert.ok(bundled.startsWith(`${pathToFileURL(outDir).href}/`), `${specifier} redirects outside the bundle directory: ${bundled}`);
    }
  } finally {
    await rm(outDir, { recursive: true, force: true });
  }
});
