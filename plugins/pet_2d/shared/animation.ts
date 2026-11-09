import { isRecord } from "@yinfengwindy/shiori-pet";

/** Provider-owned controls; all amplitudes are relative to the model's anchors. */
export const animationControls = {
  idleSway: { label: "摆动幅度", min: 0, max: 2, step: 0.05, initial: 1, unit: "×" },
  breathing: { label: "呼吸幅度", min: 0, max: 2, step: 0.05, initial: 1, unit: "×" },
  motionSpeed: { label: "待机速度", min: 0.25, max: 2, step: 0.05, initial: 1, unit: "×" },
  blinkInterval: { label: "眨眼间隔", min: 1, max: 12, step: 0.1, initial: 4.1, unit: "秒" },
  hairSway: { label: "摆动强度", min: 0, max: 2, step: 0.05, initial: 1, unit: "×" },
  hairStiffness: { label: "头发硬度", min: 0.5, max: 2, step: 0.05, initial: 1, unit: "×" },
  hairDamping: { label: "阻尼", min: 0.4, max: 2, step: 0.05, initial: 1, unit: "×" },
  voiceMouthGain: { label: "语音口型灵敏度", min: 0, max: 3, step: 0.05, initial: 1, unit: "×" },
  faceMouthGain: { label: "面捕口型灵敏度", min: 0, max: 3, step: 0.05, initial: 1, unit: "×" },
} as const;

/** Settings are indexed by the immutable package hash, shared by identical imports. */
export type AnimationSettings = { [K in keyof typeof animationControls]: number };
/** Validates every control at the RPC/storage boundary without coercion. */
export function readAnimationSettings(value: unknown): AnimationSettings {
  if (!isRecord(value)) throw new Error("动画参数必须为对象");
  const result = { idleSway: 1, breathing: 1, motionSpeed: 1, blinkInterval: 4.1, hairSway: 1, hairStiffness: 1, hairDamping: 1, voiceMouthGain: 1, faceMouthGain: 1 };
  for (const key of Object.keys(value)) if (!Object.hasOwn(animationControls, key)) throw new Error(`未知动画参数 ${key}`);
  for (const key of Object.keys(animationControls) as (keyof AnimationSettings)[]) {
    const spec = animationControls[key], number = value[key] === undefined ? spec.initial : value[key];
    if (typeof number !== "number" || !Number.isFinite(number) || number < spec.min || number > spec.max) throw new Error(`${spec.label}超出范围`);
    result[key] = number;
  }
  return result;
}
/** Fresh defaults for one model; callers never mutate a shared settings object. */
export function defaultAnimationSettings(): AnimationSettings { return readAnimationSettings({}); }
/** Installed models of the role being edited, with its current desktop selection. */
export type AnimationModel = { modelId: string; name: string };
/** The current role's package picker, independent of whether its pet is shown. */
export type AnimationCatalog = { models: AnimationModel[]; selectedModelId: string | null };
