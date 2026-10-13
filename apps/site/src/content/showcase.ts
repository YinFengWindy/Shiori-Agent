/**
 * The showcase's demo clips, in page order: the one list of their ids. The
 * clips' Remotion source (apps/site-video) renders one composition per id
 * into `assets/showcase/<id>.{webm,mp4}` and `<id>-poster.jpg`, which
 * `lib/siteAssets.ts` picks up by the same ids.
 */
export const SHOWCASE_CLIP_IDS = ["memory", "affection", "proactive", "channels", "plugins"] as const;

/** A demo clip of the showcase. */
export type ShowcaseClipId = (typeof SHOWCASE_CLIP_IDS)[number];

/**
 * Size budget of every rendered clip file (each format), so the showcase
 * stays light on a phone: the render script refuses to write past it and
 * the build test checks the emitted files against it.
 */
export const SHOWCASE_CLIP_MAX_BYTES = 1.5 * 1024 * 1024;

/** One feature block of the home page showcase (#772). */
export interface ShowcaseFeature {
  /** The demo clip beside it (also the block's anchor id). */
  readonly clip: ShowcaseClipId;
  /** Short title, in the story type. */
  readonly title: string;
  /** One short line under the title. */
  readonly line: string;
  /** What the demo clip shows, for its accessible name. */
  readonly clipLabel: string;
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
    clipLabel: "演示：聊天中逐条出现对话，吟风想起一起看过的旅行随笔并接上话题",
  },
  {
    clip: "affection",
    title: "从厌恶，到挚爱",
    line: "好感度随相处慢慢变化，七个阶段，一点点走近。",
    clipLabel: "演示：角色页上的好感度随三次互动各加 3 点，阶段从熟悉升到朋友",
  },
  {
    clip: "proactive",
    title: "太久不理她，她会来找你",
    line: "依关系与互动主动开口，也能自己安排任务与定时。",
    clipLabel: "演示：聊天停下三小时后，吟风接连发来两条消息通知",
  },
  {
    clip: "channels",
    title: "出门在外，也躲不掉",
    line: "Telegram、QQ、飞书都能接，到哪儿都是同一个她。",
    clipLabel: "演示：Telegram、QQ 群聊与飞书窗口依次弹出，吟风在每个窗口里发来消息",
  },
  {
    clip: "plugins",
    title: "不只是陪你聊天",
    line: "文件、搜索、shell 帮你做事；故事模式、桌宠、生图按需开启。",
    clipLabel: "演示：吟风调用读取文件、搜索与 shell 工具后回复，随后是故事模式菜单与剧情画面，最后以桌宠形象展示生成的图片",
  },
];
