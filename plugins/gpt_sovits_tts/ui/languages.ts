import type { VoiceLanguage } from "../shared/contracts";

/** Readable labels retain the upstream api_v2 language identifiers. */
export const voiceLanguages: Array<{ value: VoiceLanguage; label: string }> = [
  { value: "auto", label: "自动识别" }, { value: "auto_yue", label: "自动识别（粤语）" },
  { value: "zh", label: "中文混合" }, { value: "en", label: "英语" }, { value: "ja", label: "日语混合" },
  { value: "ko", label: "韩语混合" }, { value: "yue", label: "粤语混合" },
  { value: "all_zh", label: "中文" }, { value: "all_ja", label: "日语" },
  { value: "all_ko", label: "韩语" }, { value: "all_yue", label: "粤语" },
];

/** Finds a declared language without casting an arbitrary select value. */
export function voiceLanguage(value: string) { return voiceLanguages.find((option) => option.value === value)?.value; }
