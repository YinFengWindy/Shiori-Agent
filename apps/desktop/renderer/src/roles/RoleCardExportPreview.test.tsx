import assert from "node:assert/strict";
import { it } from "node:test";
import { act } from "react";
import { mountTestComponent } from "@yinfengwindy/shiori-sdk/testing";
import type { RoleCardExportPreview as ExportPreview } from "../../../src/bridge/roleCardExportContract";
import { RoleCardExportPreview } from "./RoleCardExportPreview";

const preview: ExportPreview = {
  export_id: "snapshot", name: "小诗", description: "简介", format: "charx", size: 128,
  character: { profile: "资料", personality: "", behavior_rules: "", response_constraints: "", nickname: "" },
  assets: [{ preview_url: "data:image/png;base64,YQ==", labels: ["头像"] }, { preview_url: "data:image/png;base64,Yg==", labels: ["背景", "心情 · neutral"] }],
};

it("switches the actual large image when a gallery thumbnail is selected", async () => {
  const view = await mountTestComponent(<RoleCardExportPreview preview={preview} format="charx" loading={false} />);
  try {
    assert.equal(view.container.querySelector('img[alt="头像"]')?.getAttribute("src"), preview.assets[0].preview_url);
    const button = view.container.querySelector<HTMLButtonElement>('button[aria-label="预览 背景、心情 · neutral"]');
    assert.ok(button);
    await act(async () => button.click());
    assert.equal(button.getAttribute("aria-pressed"), "true");
    assert.equal(view.container.querySelector('img[alt="背景、心情 · neutral"]')?.getAttribute("src"), preview.assets[1].preview_url);
    assert.equal(view.container.querySelectorAll("button").length, 2);
  } finally { await view.cleanup(); }
});

it("uses a JSON file preview instead of implying images are exported", async () => {
  const view = await mountTestComponent(<RoleCardExportPreview preview={{ ...preview, assets: [], format: "json" }} format="json" loading={false} />);
  try {
    assert.match(view.container.textContent ?? "", /小诗.json/);
    assert.equal(view.container.querySelector("img"), null);
    assert.equal(view.container.querySelector("button"), null);
  } finally { await view.cleanup(); }
});

it("shows a stable loading frame and an explicit empty-image state", async () => {
  const view = await mountTestComponent(<RoleCardExportPreview preview={null} format="charx" loading />);
  try { assert.match(view.container.querySelector('[role="status"]')?.textContent ?? "", /正在准备预览/); }
  finally { await view.cleanup(); }
  const empty = await mountTestComponent(<RoleCardExportPreview preview={{ ...preview, assets: [] }} format="charx" loading={false} />);
  try { assert.match(empty.container.textContent ?? "", /无图片素材/); }
  finally { await empty.cleanup(); }
});
