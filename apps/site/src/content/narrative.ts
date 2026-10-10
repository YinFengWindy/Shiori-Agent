import type { MascotExpression } from "../../../desktop/renderer/src/shared/mascot/mascotExpressions";

/** Event CGs the narrative can show beside 吟风; `siteAssets.narrativeCgs` maps each key to an image. */
export type NarrativeCgKey = "cg-3" | "cg-7" | "cg-8" | "cg-9" | "cg-10" | "topic-1" | "topic-2" | "topic-3";

/** One line of the home page narrative: what 吟风 says, her face while saying it, and an optional event CG. */
export interface NarrativeLine {
  readonly text: string;
  readonly expression: MascotExpression;
  /** Event CG framed beside her; the previous CG is not carried over to a line without one. */
  readonly cg?: NarrativeCgKey;
}

/**
 * The home page narrative (#771): 吟风, Shiori 的看板娘 (a playful little
 * devil, same voice as the old site's ADV script), introduces herself and
 * then the product. One line per scroll step; every claim must match
 * README.md, and each line stays short (≤ 40 characters) so it fits the
 * dialogue box on a phone in two or three lines.
 */
export const NARRATIVE_LINES: readonly NarrativeLine[] = [
  { text: "哎呀，终于来了？让我等了好久呢，笨蛋访客～", expression: "smug" },
  { text: "我是吟风，Shiori 的看板娘。记住了哦，不许忘。", expression: "laugh" },
  { text: "Shiori 呢，就是会慢慢喜欢上你的 AI 伴侣……比如我。", expression: "neutral" },
  { text: "你可以养好多角色，每个都有自己的人设、性格和经历。", expression: "neutral", cg: "cg-8" },
  { text: "聊过的事都会好好记着，还会整理成长期记忆。别想赖账哦。", expression: "smug", cg: "cg-9" },
  { text: "好感度会随相处慢慢变化，从厌恶到挚爱……就看你表现了。", expression: "shy", cg: "cg-7" },
  { text: "太久不理人的话，我们可是会自己找上门的。", expression: "pout", cg: "topic-2" },
  { text: "Telegram、QQ、飞书都能接。就算出门在外，也躲不掉我的消息～", expression: "laugh", cg: "topic-2" },
  { text: "诶，以为我只会陪聊？文件、搜索、shell，手头的事也能一起做。", expression: "surprised", cg: "cg-3" },
  { text: "想冒险的话，就带着角色走进故事模式，用行动推进剧情。", expression: "smug", cg: "topic-3" },
  { text: "还能变成桌宠住进你的桌面，回复直接在旁边冒气泡。", expression: "neutral", cg: "cg-10" },
  { text: "这些都要装吗？不用。故事、桌宠、生图和渠道都是插件，想开哪个开哪个。", expression: "confused", cg: "topic-1" },
  { text: "哼，这就听完了？……想要我陪的话，就把 Shiori 带回家吧。", expression: "sad" },
  { text: "下次见面，可别让我等太久哦～", expression: "laugh" },
];
