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
  [/超过大小限制|数量超过限制/, "角色卡文件太大"],
  [/不是有效 ZIP|card\.json/, "角色卡包已损坏"],
  [/JSON|必须是对象/, "角色卡内容无法解析"],
  [/不支持加密/, "不支持加密的角色卡包"],
  [/不支持的角色卡格式|格式不支持/, "不支持这种文件格式"],
  [/不存在/, "找不到这个文件"],
];

/**
 * Maps a card import failure to user-facing Chinese. Unknown causes pass
 * through unchanged (they are already the bridge's Chinese message).
 */
export function describeRoleCardImportError(raw: string): RoleCardImportErrorView {
  const cause = raw.trim();
  const friendly = friendlyCauses.find(([pattern]) => pattern.test(cause))?.[1];
  return friendly
    ? { message: `角色导入失败：${friendly}`, detail: cause }
    : { message: `角色导入失败：${cause}`, detail: "" };
}
