import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { describeRoleCardImportError } from "./roleCardImportErrors";

describe("describeRoleCardImportError", () => {
  it("replaces the metadata jargon with plain Chinese and keeps it as detail", () => {
    assert.deepEqual(describeRoleCardImportError("角色卡图片缺少 chara 或 ccv3 metadata"), {
      message: "角色卡读取失败：这张图片里没有找到角色卡数据",
      detail: "角色卡图片缺少 chara 或 ccv3 metadata",
    });
  });

  it("maps the other card-import causes", () => {
    assert.equal(describeRoleCardImportError("角色卡包超过大小限制").message, "角色卡读取失败：角色卡包超过大小限制");
    assert.equal(describeRoleCardImportError("角色卡包不是有效 ZIP").message, "角色卡读取失败：角色卡包已损坏");
    assert.equal(describeRoleCardImportError("角色卡 JSON 无效").message, "角色卡读取失败：角色卡内容无法解析");
    assert.equal(describeRoleCardImportError("不支持的角色卡格式").message, "角色卡读取失败：不支持这种文件格式");
  });

  it("passes an unknown cause through without a detail", () => {
    assert.deepEqual(describeRoleCardImportError("桥接服务已断开"), { message: "角色卡读取失败：桥接服务已断开", detail: "" });
  });
});


it("keeps archive limits distinct and treats cleanup as a cancelled import", () => {
  for (const cause of ["角色卡包内条目过多（最多 128 个条目）", "角色卡包单条目超过大小限制（最多 25 MiB）", "角色卡源文件超过大小限制（最多 50 MiB）", "角色卡包解压总大小超过限制（最多 200 MiB）"]) {
    assert.ok(describeRoleCardImportError(cause).message.endsWith(cause));
  }
  assert.match(describeRoleCardImportError("角色卡包根目录缺少 card.json").message, /缺少角色信息文件/);
  assert.equal(describeRoleCardImportError(new Error("unlink denied"), "cleanup").message, "已退出导入，但临时预览清理失败");
});

it("does not translate a missing staging record into a missing source file", () => {
  const view = describeRoleCardImportError("角色卡预览不存在，请重新读取角色卡", "commit");
  assert.equal(view.message, "角色卡导入未完成：角色卡预览不存在，请重新读取角色卡");
});
