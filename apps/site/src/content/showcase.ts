/**
 * The showcase's features, in page order: the one list of their ids. Each
 * has a still, a screenshot of the real desktop app captured by
 * apps/site-video into `assets/showcase/<id>.webp`, which
 * `lib/siteAssets.ts` picks up by the same ids, and a Remotion demo clip of
 * the same id (the page shows the stills, not the videos: #790).
 */
export const SHOWCASE_CLIP_IDS = ["memory", "affection", "proactive", "channels", "plugins"] as const;

/** A demo clip of the showcase. */
export type ShowcaseClipId = (typeof SHOWCASE_CLIP_IDS)[number];

/**
 * Size budget of every showcase still, so the showcase stays light on a slow
 * line: the stills script refuses to write past it and the build test checks
 * the emitted files against it.
 */
export const SHOWCASE_STILL_MAX_BYTES = 150 * 1024;

/** One feature block of the home page showcase (#772). */
export interface ShowcaseFeature {
  /** The feature id: its still sits beside it (also the block's anchor id). */
  readonly clip: ShowcaseClipId;
  /** Short title, in the story type. */
  readonly title: string;
  /** One short line under the title. */
  readonly line: string;
  /** What the still shows, as its alt text. */
  readonly stillAlt: string;
}

/**
 * The showcase, top to bottom. Every claim must match README.md; titles stay
 * a few words and lines one sentence, so a block reads at a glance on a phone.
 */
export const SHOWCASE_FEATURES: readonly ShowcaseFeature[] = [
  {
    clip: "memory",
    title: "聊过的事，她都记得",
    line: "每个角色都有自己的人设与经历，往事会整理成长期记忆。",
    stillAlt: "角色页截图：吟风的记忆时间线，记着约好周六下午去旧书店、你喝咖啡不加糖、小时候在海边住过一个夏天",
  },
  {
    clip: "affection",
    title: "从厌恶，到挚爱",
    line: "好感度随相处慢慢变化，七个阶段，一点点走近。",
    stillAlt: "角色页截图：好感度 41，处在朋友阶段，下面按天列着每次 +1、+2 的小变化和原因",
  },
  {
    clip: "proactive",
    title: "太久不理她，她会来找你",
    line: "依关系与互动主动开口，也能自己安排任务与定时。",
    stillAlt: "聊天截图：道过晚安后一整天没有消息，吟风接连主动发来两条",
  },
  {
    clip: "channels",
    title: "出门在外，也躲不掉",
    line: "Telegram、QQ、飞书都能接，到哪儿都是同一个她。",
    stillAlt: "聊天截图：打开角色的手机，QQ 群「周末读书会」里吟风替你回了大家的消息",
  },
  {
    clip: "plugins",
    title: "不只是陪你聊天",
    line: "文件、搜索、shell 帮你做事；故事模式、桌宠、生图按需开启。",
    stillAlt: "聊天截图：吟风的回复上方展开了 read_file、web_search 与 shell 三次工具调用",
  },
];
