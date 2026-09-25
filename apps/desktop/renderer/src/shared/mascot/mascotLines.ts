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
 * A face 吟风 makes, with or without a line. A cue without `text` shows only
 * her face (frequent success / info toasts, where a sentence every time
 * would be spam).
 */
export type MascotCue = {
  readonly expression: MascotExpression;
  readonly text?: string;
};

const face = (expression: MascotExpression): MascotCue => ({ expression });

/**
 * Toasts 吟风 fronts (see `FeedbackToast.persona`). The rule for when she
 * speaks (docs/_handbook/design-system.md 「看板娘」):
 *
 * - error / warning: always a line — something went wrong, she says so
 *   first; the original message follows and the cause stays behind 「详情」.
 * - success / info: only her face by default (`success`, `info` below): these
 *   are the frequent ones (已复制, 已保存, 已加入素材库…).
 * - A line on a success toast is reserved for rare milestones (a role
 *   created, imported or deleted, the connection back); the call site asks
 *   for it by name.
 */
export const feedbackPersonaLines = {
  /** Any host error without a more specific line, when a 详情 cause follows. */
  generic: line("confused", "出了点状况……详情我放在下面了。"),
  /** `generic` for an error without a 详情 cause (the line must not promise one). */
  genericBrief: line("confused", "唔，出了点状况……"),
  /** Any warning without a more specific line. */
  warning: line("confused", "嗯？这里好像有点不对劲。"),
  /** Sending failed because the role has no usable model. */
  modelMissing: line("pout", "还没给我接模型呢，先去选一个！"),
  /** A role card could not be imported. */
  roleImportFailed: line("confused", "这张角色卡我读不懂……换一张试试？"),
  /** Success default: her face only. */
  success: face("laugh"),
  /** Info default: her face only. */
  info: face("neutral"),
  /** A new role was created (milestone). */
  roleCreated: line("laugh", "新朋友来啦！要好好相处哦。"),
  /** A role card was imported (milestone). */
  roleImported: line("smug", "角色卡读好了，快去打个招呼吧。"),
  /** A role was deleted (milestone). */
  roleDeleted: line("sad", "删掉了……才、才没有舍不得呢。"),
  /** The bridge came back after a disconnect (milestone). */
  bridgeRecovered: line("laugh", "连上了！刚才可吓我一跳。"),
} satisfies Record<string, MascotCue>;

/** Which of `feedbackPersonaLines` fronts a toast. */
export type FeedbackPersona = keyof typeof feedbackPersonaLines;

/**
 * Confirmation dialogs (`ConfirmDialog`'s `persona`): her line leads the
 * dialog, the factual consequence text follows it unchanged. The face
 * follows the intent: deleting → 担心, discarding edits → 鼓脸, restarting →
 * 惊讶, trusting / installing → 疑惑 / 普通.
 */
export const confirmPersonaLines = {
  /** Any destructive confirmation without a more specific line. */
  destructive: line("sad", "删掉就回不来了哦，想好了吗？"),
  /** Any other confirmation without a more specific line. */
  confirm: line("neutral", "要继续吗？我等你一句话。"),
  deleteRole: line("sad", "真的要删掉 TA 吗？我会有点……舍不得。"),
  deleteModel: line("sad", "这个模型要删掉吗？想好了哦。"),
  deleteAsset: line("sad", "这张图要删掉吗？明明挺好看的……"),
  deleteAssetCategory: line("sad", "整个分类都不要了？好可惜……"),
  deleteKnowledgeEntry: line("confused", "这条要从知识库里划掉吗？"),
  discardChanges: line("pout", "改了半天，就这样不要了？"),
  restartDuringTurn: line("surprised", "诶？还在聊着呢，现在就重启？"),
  trustPlugin: line("confused", "陌生的插件……你真的信得过它？"),
  installPlugin: line("neutral", "要来新伙伴了？先确认它可靠哦。"),
  updatePlugin: line("neutral", "插件要更新啦，确认一下来源吧。"),
  uninstallPlugin: line("sad", "要和这个插件说再见了吗？"),
} satisfies Record<string, MascotLine>;

/**
 * In-page error blocks (`InlineError`'s `persona`): her face and line first,
 * the original message after it, the cause behind 「详情」.
 */
export const inlineErrorLines = {
  /** Any in-page error without a more specific line. */
  generic: line("confused", "唔，这里出了点问题……"),
  settingsSaveFailed: line("sad", "没保存上……要再试一次吗？"),
  settingsLoadFailed: line("sad", "设置没读出来……先别急着改哦。"),
  pluginsLoadFailed: line("sad", "插件列表没读出来……"),
  pluginConfigLoadFailed: line("sad", "这个插件的配置没读出来……"),
  connectionTestFailed: line("confused", "连不上呢……地址和密钥再对一下？"),
  microphoneTestFailed: line("confused", "我没听到声音……麦克风还好吗？"),
  chatTurnFailed: line("sad", "这句没能送到……"),
} satisfies Record<string, MascotLine>;

/** Which of `inlineErrorLines` fronts an in-page error. */
export type InlineErrorPersona = keyof typeof inlineErrorLines;

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
  failed: line("confused", "更新没弄成……待会儿再试试？"),
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
