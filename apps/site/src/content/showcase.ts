/**
 * The showcase's demo clips, in page order: the one list of their ids. The
 * clips' Remotion source (apps/site-video) has one composition per id and
 * renders a still of each into `assets/showcase/<id>.webp`, which
 * `lib/siteAssets.ts` picks up by the same ids (the page shows the stills,
 * not the videos: #790).
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
  /** The demo clip whose still sits beside it (also the block's anchor id). */
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
    stillAlt: "聊天截图：吟风的回复上方浮出一枚书签，写着「想起：一起翻过的旅行随笔 · 海边灯塔那一页」",
  },
  {
    clip: "affection",
    title: "从厌恶，到挚爱",
    line: "好感度随相处慢慢变化，七个阶段，一点点走近。",
    stillAlt: "角色页截图：好感度卡片列出三次互动各加 3 点，阶段已从熟悉升到朋友",
  },
  {
    clip: "proactive",
    title: "太久不理她，她会来找你",
    line: "依关系与互动主动开口，也能自己安排任务与定时。",
    stillAlt: "聊天截图：屏幕右下角叠着吟风接连发来的两条消息通知",
  },
  {
    clip: "channels",
    title: "出门在外，也躲不掉",
    line: "Telegram、QQ、飞书都能接，到哪儿都是同一个她。",
    stillAlt: "截图：Telegram 私聊、QQ 群聊与飞书私聊三个窗口并排，吟风在每个窗口里都发来了消息",
  },
  {
    clip: "plugins",
    title: "不只是陪你聊天",
    line: "文件、搜索、shell 帮你做事；故事模式、桌宠、生图按需开启。",
    stillAlt: "聊天截图：吟风正在调用的读取文件、搜索与 shell 三个工具依次列在对话里",
  },
];
