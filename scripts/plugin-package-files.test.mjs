import assert from "node:assert/strict";
import test from "node:test";
import { distributablePath, packageFile } from "./plugin-package-files.mjs";

test("manifest paths cannot escape or include source-only development artifacts", () => {
  for (const name of ["/absolute", "../escape", "backend/../escape", "C:/private", "backend\\file.py", "backend//file.py"]) {
    assert.throws(() => packageFile("package", name), /Invalid package path/);
  }
  for (const name of ["backend/.venv/lib.py", "backend/tests/test_api.py", "backend/__pycache__/api.pyc", ".env", "node_modules/library.js"]) {
    assert.equal(distributablePath(name), false);
  }
  assert.equal(distributablePath("backend/model_client.py"), true);
  assert.equal(distributablePath("docs/configuration.md"), true);
});
