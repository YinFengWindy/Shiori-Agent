/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { parseInstalledDesktopPlugins } from "./types";

describe("installed desktop plugin records", () => {
  it("accepts only enabled host contracts with matching identities and declared capabilities", () => {
    const parsed = parseInstalledDesktopPlugins([{
      plugin_id: "desktop-pet",
      package_dir: "C:\\plugins\\desktop-pet\\1.0.0",
      enabled: true,
      manifest: {
        plugin_id: "desktop-pet",
        name: "Desktop Pet",
        capabilities: ["desktop.overlay", "plugin.rpc"],
        rpc_methods: [{ method: "pet.state", remote_name: "pet_state" }],
        desktop_contributions: [{
          id: "pet-overlay",
          kind: "overlay",
          entrypoint: "desktop/index.html",
          width: 480,
          height: 680,
          transparent: true,
          always_on_top: true,
        }],
      },
    }, {
      plugin_id: "spoofed",
      package_dir: "C:\\plugins\\spoofed",
      enabled: true,
      manifest: {
        plugin_id: "different",
        name: "Spoofed",
        capabilities: [],
        rpc_methods: [],
        desktop_contributions: [],
      },
    }]);

    assert.equal(parsed.length, 1);
    assert.equal(parsed[0]?.pluginId, "desktop-pet");
    assert.deepEqual([...parsed[0]!.capabilities], ["desktop.overlay", "plugin.rpc"]);
    assert.equal(parsed[0]?.contributions[0]?.transparent, true);
  });
});
