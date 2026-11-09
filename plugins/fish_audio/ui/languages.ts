import type { TextLanguage } from "../shared/contracts";

/** Languages with dedicated Fish text-normalization rules; auto preserves detection. */
export const textLanguages: Array<{ value: TextLanguage; label: string }> = [
  { value: "auto", label: "自动识别" },
  { value: "zh-CN", label: "简体中文" },
  { value: "zh-TW", label: "繁体中文" },
  { value: "en", label: "英语" },
  { value: "ja", label: "日语" },
  { value: "ko", label: "韩语" },
  { value: "es-ES", label: "西班牙语（西班牙）" },
  { value: "es-MX", label: "西班牙语（墨西哥）" },
  { value: "fr", label: "法语" },
  { value: "de", label: "德语" },
  { value: "it", label: "意大利语" },
  { value: "pt-BR", label: "葡萄牙语（巴西）" },
  { value: "ru", label: "俄语" },
  { value: "ar", label: "阿拉伯语" },
  { value: "tr", label: "土耳其语" },
  { value: "fil", label: "菲律宾语" },
];

/** Narrow a select value to a supported language without casting arbitrary strings. */
export function textLanguage(value: string) {
  return textLanguages.find((option) => option.value === value)?.value;
}
