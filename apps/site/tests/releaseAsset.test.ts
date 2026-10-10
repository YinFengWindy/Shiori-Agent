import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { pickWindowsInstaller } from "../src/lib/releaseAsset";

const download = (name: string) => `https://github.com/YinFengWindy/Shiori-Agent/releases/download/v0.5.2/${name}`;
const asset = (name: string) => ({ name, browser_download_url: download(name) });

describe("pickWindowsInstaller", () => {
  it("picks the versioned Windows installer, skipping its blockmap and other assets", () => {
    const release = {
      tag_name: "v0.5.2",
      assets: [asset("Shiori-Setup-0.5.2.exe.blockmap"), asset("latest.yml"), asset("Shiori-Setup-0.5.2.exe")],
    };
    assert.deepEqual(pickWindowsInstaller(release), { url: download("Shiori-Setup-0.5.2.exe"), version: "v0.5.2" });
  });

  it("returns null when the release has no installer", () => {
    assert.equal(pickWindowsInstaller({ tag_name: "v0.5.2", assets: [asset("Shiori-Setup-0.5.2.exe.blockmap"), asset("latest.yml")] }), null);
    assert.equal(pickWindowsInstaller({ tag_name: "v0.5.2", assets: [] }), null);
  });

  it("returns null for a response that is not a release (rate-limit error, garbage)", () => {
    assert.equal(pickWindowsInstaller({ message: "API rate limit exceeded" }), null);
    assert.equal(pickWindowsInstaller(null), null);
    assert.equal(pickWindowsInstaller("Shiori-Setup-0.5.2.exe"), null);
  });

  it("only links GitHub-hosted downloads", () => {
    const release = { tag_name: "v0.5.2", assets: [{ name: "Shiori-Setup-0.5.2.exe", browser_download_url: "https://example.com/Shiori-Setup-0.5.2.exe" }] };
    assert.equal(pickWindowsInstaller(release), null);
  });

  it("still links the installer when the release has no tag name", () => {
    assert.deepEqual(pickWindowsInstaller({ assets: [asset("Shiori-Setup-0.5.2.exe")] }), { url: download("Shiori-Setup-0.5.2.exe"), version: null });
  });
});
