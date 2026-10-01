import { errorFeedback } from "@shiori/plugin-sdk/host-internal";

/** A role card import failure as the user reads it, with the bridge's own wording kept as detail. */
export type RoleCardImportErrorView = {
  message: string;
  /** The raw cause; empty when the message already is it. */
  detail: string;
};

// Checked in order against the backend's card-import errors
// (`core/roles/card_import/*`); the first match wins.
const friendlyCauses: ReadonlyArray<readonly [RegExp, string]> = [
  [/缺少 chara 或 ccv3 metadata/, "这张图片里没有找到角色卡数据"],
  [/角色卡图片无效|图片无效/, "这张图片无法读取"],
  [/角色卡包文件数量超过限制/, "角色卡包内条目过多"],
  [/根目录缺少 card\.json/, "角色卡包缺少角色信息文件"],
  [/不是有效 ZIP/, "角色卡包已损坏"],
  [/JSON|必须是对象/, "角色卡内容无法解析"],
  [/不支持加密/, "不支持加密的角色卡包"],
  [/不支持的角色卡格式|格式不支持/, "不支持这种文件格式"],
  [/不存在/, "找不到这个文件"],
];

/**
 * Keeps the failed import phase explicit, with readable domain causes and
 * scrubbed technical context available behind the detail disclosure.
 */
export function describeRoleCardImportError(error: unknown, phase: "preview" | "commit" | "cleanup" = "preview"): RoleCardImportErrorView {
  const view = errorFeedback(error, "请查看详情后重试");
  const cause = view.message;
  if (phase === "cleanup") return { message: "已退出导入，但临时预览清理失败", detail: [cause, view.detail].filter(Boolean).join("\n") };
  const prefix = phase === "preview" ? "角色卡读取失败" : "角色卡导入未完成";
  // Only preview reads parse the source file; commit failures can name missing
  // staging records or role data and must retain their own recovery advice.
  const friendly = phase === "preview" ? friendlyCauses.find(([pattern]) => pattern.test(cause))?.[1] : undefined;
  return friendly
    ? { message: `${prefix}：${friendly}`, detail: [cause, view.detail].filter(Boolean).join("\n") }
    : { message: `${prefix}：${cause}`, detail: view.detail };
}
