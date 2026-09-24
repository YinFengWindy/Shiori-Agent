import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { describeRoleCardImportError } from "./roleCardImportErrors";

describe("describeRoleCardImportError", () => {
  it("replaces the metadata jargon with plain Chinese and keeps it as detail", () => {
    assert.deepEqual(describeRoleCardImportError("角色卡图片缺少 chara 或 ccv3 metadata"), {
      message: "角色导入失败：这张图片里没有找到角色卡数据",
      detail: "角色卡图片缺少 chara 或 ccv3 metadata",
    });
  });

  it("maps the other card-import causes", () => {
    assert.equal(describeRoleCardImportError("角色卡包超过大小限制").message, "角色导入失败：角色卡文件太大");
    assert.equal(describeRoleCardImportError("角色卡包不是有效 ZIP").message, "角色导入失败：角色卡包已损坏");
    assert.equal(describeRoleCardImportError("角色卡 JSON 无效").message, "角色导入失败：角色卡内容无法解析");
    assert.equal(describeRoleCardImportError("不支持的角色卡格式").message, "角色导入失败：不支持这种文件格式");
  });

  it("passes an unknown cause through without a detail", () => {
    assert.deepEqual(describeRoleCardImportError("桥接服务已断开"), { message: "角色导入失败：桥接服务已断开", detail: "" });
  });
});
