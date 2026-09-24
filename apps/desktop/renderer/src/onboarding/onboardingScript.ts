import type { MascotExpression } from "../shared/mascot/mascotExpressions";

/** One line 吟风 speaks in the first-run guide, with the face she makes. */
export type MascotLine = { readonly expression: MascotExpression; readonly text: string };

/**
 * What the guide is showing: a setup step, the bridge being unreachable
 * ("offline"), or a failure while data is available ("failed").
 */
export type OnboardingScene = "loading" | "model" | "role" | "workspace" | "offline" | "failed";

/** Something the user did in a form that 吟风 answers. */
export type OnboardingReaction =
  | "connectionOk"
  | "connectionFailed"
  | "modelSaveFailed"
  | "avatarPicked"
  | "importFailed"
  | "roleCreateFailed"
  | "skipModel"
  | "skipRole";

const say = (expression: MascotExpression, text: string): MascotLine => ({ expression, text });

/*
 * 吟风's lines (owner-approved, see #362 stage 8): short, in her voice —
 * sharp-tongued little devil who is secretly afraid of being alone. These
 * lines are the one sanctioned exception to "no narrating copy" in AGENTS.md;
 * the forms themselves stay label-only. Keep each line within 40 characters
 * and every product claim true (single timeline per role, channels are plugins).
 */
const openingLines = [
  say("smug", "哟，新来的？我是吟风，Shiori 的看板娘。"),
  say("neutral", "开始之前，得先帮你把几样东西准备好。"),
];

const reactionLines: Record<OnboardingReaction, MascotLine> = {
  connectionOk: say("laugh", "通了通了！看来你还挺靠谱嘛。"),
  connectionFailed: say("sad", "连不上……是不是密钥抄错了？"),
  modelSaveFailed: say("confused", "咦，没存上？再试一次看看。"),
  avatarPicked: say("surprised", "哇，好可爱……比我差一点点就是了。"),
  importFailed: say("confused", "这张图里好像没有角色卡数据？"),
  roleCreateFailed: say("sad", "唔，没建成……再检查一下？"),
  skipModel: say("pout", "跳过？好吧，以后去设置里也能弄。"),
  skipRole: say("pout", "不建了？好吧，以后在角色页也能建。"),
};

/**
 * The lines that open a scene. The greeting plays once, before the model
 * step of a fresh visit; a guide resumed at a later step starts right there.
 */
export function onboardingSceneLines(scene: OnboardingScene, options: { greet: boolean; roleName: string }): MascotLine[] {
  switch (scene) {
    case "loading":
      return [];
    case "model":
      return [...(options.greet ? openingLines : []), say("neutral", "首先给 Shiori 接上一个大模型，不然我连话都说不了。")];
    case "role":
      return [say("smug", "接下来，创建你的第一个角色吧。"), say("pout", "……不是我也行啦，哼。")];
    case "workspace":
      return [say("laugh", `准备好啦！去和 ${options.roleName} 打个招呼吧。`), say("shy", "……偶尔也要回来看看我哦。")];
    case "offline":
      return [say("sad", "咦，后台还没醒过来……")];
    case "failed":
      return [say("confused", "诶，没能进去……再试一次？")];
  }
}

/** 吟风's answer to one form action. */
export function onboardingReactionLine(reaction: OnboardingReaction): MascotLine {
  return reactionLines[reaction];
}
