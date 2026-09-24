/**
 * Maps a role's free-form mood label onto one of five motion tones. Moods are
 * whatever the role author (or an imported role card) put in the mood catalog
 * — Chinese words such as 「开心」「害羞」, or card emotion names such as
 * `joy` / `embarrassment` — so the mapping matches keywords instead of an
 * enumeration, and anything unrecognised is `calm`.
 *
 * The tone picks the mood pill's colours and the particle burst played when
 * the mood changes (see `moodBurst.ts`).
 */
export type MoodTone = "happy" | "shy" | "sad" | "angry" | "calm";

/**
 * Keywords per tone, checked in this order. `shy` comes before `happy` so
 * 「心动」「甜蜜」-like labels read as shy, and `angry` before `sad` so
 * 「委屈生气」 shakes. Latin keywords are matched case-insensitively.
 */
const toneKeywords: ReadonlyArray<readonly [MoodTone, readonly string[]]> = [
  ["angry", ["生气", "愤怒", "恼", "气鼓鼓", "火大", "不满", "不爽", "烦躁", "暴躁", "吃醋", "嫉妒", "哼", "anger", "angry", "annoy", "mad", "furious", "disgust", "disapprov", "jealous"]],
  ["shy", ["害羞", "羞", "脸红", "心动", "腼腆", "扭捏", "撒娇", "暧昧", "甜蜜", "喜欢", "爱慕", "shy", "blush", "embarrass", "love", "desire", "flustered"]],
  ["sad", ["难过", "伤心", "悲", "哭", "泪", "失落", "沮丧", "委屈", "低落", "忧", "寂寞", "孤独", "想念", "思念", "心疼", "遗憾", "sad", "grief", "cry", "lonely", "disappoint", "remorse", "sorrow", "upset", "hurt"]],
  ["happy", ["开心", "高兴", "快乐", "愉快", "喜悦", "欢", "兴奋", "雀跃", "得意", "满足", "幸福", "期待", "笑", "激动", "joy", "happy", "excite", "amuse", "delight", "cheer", "glad", "optimis", "pride", "grateful", "gratitude"]],
];

/** The motion tone for a mood label; unknown or empty labels are `calm`. */
export function moodTone(mood: string): MoodTone {
  const label = mood.trim().toLowerCase();
  if (!label) return "calm";
  for (const [tone, keywords] of toneKeywords) {
    if (keywords.some((keyword) => label.includes(keyword))) return tone;
  }
  return "calm";
}
