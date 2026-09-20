/// <reference types="node" />
import assert from "node:assert/strict";
import { test } from "node:test";
import { installRendererHost, rendererHost } from "./rendererHost";
import { toFileUrl } from "./format";

test("a browser host exposes only its allowlisted assets and restores the prior host", () => {
  const original = rendererHost;
  let external = "";
  const restore = installRendererHost({ localAssetUrl: (path) => path === "public-avatar" ? "./avatar.png" : "unavailable", openExternal: (url) => { external = url; } });
  // SSR deliberately fails closed; the view host itself still resolves the explicit port.
  assert.equal(rendererHost.localAssetUrl("C:/private/secret.png"), "unavailable");
  assert.equal(rendererHost.localAssetUrl("public-avatar"), "./avatar.png");
  rendererHost.openExternal("https://example.com");
  assert.equal(external, "https://example.com");
  restore();
  assert.equal(rendererHost, original);
  assert.equal(toFileUrl("private"), "shiori-asset://local/unavailable");
});
