import type { MascotExpression } from "./mascotExpressions";

/*
 * 吟风's lines outside the first-run guide (#362 stage 10, 「看板娘驻场」).
 *
 * These are an owner-approved exception to AGENTS.md's 「前端页面不要产生对
 * 功能进行叙述的文字」, like the onboarding script (#377): the mascot speaks
 * in character. Each line is at most 40 characters, in her voice (a
 * tsundere little devil who hates being alone). The owner edits the wording
 * here directly; every place that speaks reads from this one table.
 */

/** One thing 吟风 says, with the face she makes while saying it. */
export type MascotLine = {
  readonly expression: MascotExpression;
  readonly text: string;
};

/** Several lines for one situation; one is drawn at random each time. */
export type MascotLinePool = readonly [MascotLine, ...MascotLine[]];

const line = (expression: MascotExpression, text: string): MascotLine => ({ expression, text });

/** Startup-splash time bands, in local time (see `startupTimeBandAt`). */
export type StartupTimeBand = "morning" | "day" | "dusk" | "evening" | "lateNight";

/** 启动画面: one greeting per time band while the backend boots. */
export const startupGreetingLines: Record<StartupTimeBand, MascotLinePool> = {
  // 清晨 05–10
  morning: [line("neutral", "早呀。今天也要好好吃早饭哦。"), line("smug", "起这么早？该不会是想我了吧。")],
  // 白天 10–17
  day: [line("neutral", "等一下下，马上就好。"), line("smug", "别急嘛，我在帮你叫醒大家。")],
  // 傍晚 17–20
  dusk: [line("neutral", "辛苦啦，今天过得怎么样？")],
  // 夜里 20–24
  evening: [line("shy", "这么晚还来找我……才没有很高兴。")],
  // 深夜 00–05
  lateNight: [line("sad", "都几点了？聊完就快去睡！")],
};

/** 启动画面: the backend has been booting for a while (see `startupSlowAfterMs`). */
export const startupSlowLine = line("confused", "唔，今天大家起得有点慢……");

/** 启动画面: the backend failed to start; shown above 「重启连接」. */
export const startupFailedLine = line("sad", "后台没醒过来……要不要重启一下？");

/** Empty states. */
export const emptyStateLines = {
  /** No roles at all (chat sidebar, roles page), above 「新建角色」/「导入角色卡」. */
  noRoles: line("pout", "一个角色都没有？那……先陪我待会儿也行。"),
  /** Search found nothing. */
  noSearchResults: line("confused", "没找到耶，换个关键词试试？"),
} satisfies Record<string, MascotLine>;

/** The connection-lost banner, in front of its 「重启连接」 button. */
export const bridgeOfflineLine = line("sad", "和后台断开了……点一下「重启连接」试试？");

/**
 * Error toasts 吟风 fronts (see `FeedbackToast.persona`): her line becomes
 * the toast's first sentence, the original message follows it and the
 * technical cause stays folded behind 「详情」.
 */
export const feedbackPersonaLines = {
  /** Any host error without a more specific line. */
  generic: line("confused", "出了点状况……详情我放在下面了。"),
  /** Sending failed because the role has no usable model. */
  modelMissing: line("pout", "还没给我接模型呢，先去选一个！"),
} satisfies Record<string, MascotLine>;

/** Which of `feedbackPersonaLines` fronts a toast. */
export type FeedbackPersona = keyof typeof feedbackPersonaLines;

/** 设置 › 关于: lines drawn on open and on every click on her sprite. */
export const aboutIdleLines: MascotLinePool = [
  line("smug", "有什么想知道的？我心情好就告诉你。"),
  line("shy", "一直盯着我看干嘛……"),
  line("laugh", "能遇到你，Shiori 也很开心哦。"),
];

/** 设置 › 关于: what she says about the update check's outcome. */
export const aboutUpdateLines = {
  available: line("surprised", "有新版本了！要不要现在更新？"),
  current: line("neutral", "已经是最新的啦，放心吧。"),
} satisfies Record<string, MascotLine>;

/**
 * The startup band for a moment in local time: morning 05:00–09:59, day
 * 10:00–16:59, dusk 17:00–19:59, evening 20:00–23:59, late night 00:00–04:59.
 * (Independent of `scenePhaseAt`, which only picks one of three pictures.)
 */
export function startupTimeBandAt(date: Date): StartupTimeBand {
  const hour = date.getHours();
  if (hour < 5) return "lateNight";
  if (hour < 10) return "morning";
  if (hour < 17) return "day";
  if (hour < 20) return "dusk";
  return "evening";
}

/**
 * Draws one line from `pool` at random, never the same as `previous` when
 * the pool offers anything else. `random` is injectable for tests.
 */
export function pickMascotLine(pool: MascotLinePool, previous: MascotLine | null = null, random: () => number = Math.random): MascotLine {
  const candidates = pool.length > 1 && previous ? pool.filter((item) => item !== previous) : pool;
  const index = Math.min(candidates.length - 1, Math.floor(random() * candidates.length));
  return candidates[index] ?? pool[0];
}
