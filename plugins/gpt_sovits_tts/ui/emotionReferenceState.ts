import type { VoiceReference } from "../shared/contracts";

/** Validates a private mapping name without treating inherited object properties as emotions. */
export function emotionNameError(raw: string, existing: readonly string[]) {
  const name = raw.trim();
  if (!name) return "请输入情绪名称";
  if (Object.hasOwn(Object.prototype, name) || name === "prototype") return "此情绪名称不可用";
  if ([...name].some((character) => { const code = character.charCodeAt(0); return code < 32 || code === 127; })) return "情绪名称不能包含控制字符";
  if (existing.includes(name)) return "此情绪已存在";
  if (existing.length >= 64) return "最多保存 64 种情绪";
  return "";
}

/** Updates a single own mapping; removing one never rewrites the other references. */
export function updateEmotionReference(moods: Record<string, VoiceReference>, name: string, reference: VoiceReference | null) {
  if (reference) return { ...moods, [name]: reference };
  return Object.fromEntries(Object.entries(moods).filter(([key]) => key !== name));
}
