import { ArrowLeft, Check, MusicNotes, SlidersHorizontal, SpeakerHigh, Waveform } from "@phosphor-icons/react";
import { motion, useReducedMotion } from "motion/react";
import { useState } from "react";
import {
  StorySegmentedControl,
  StoryToggle,
  StoryVolumeControl,
} from "./StorySettingsControls";
import { STORY_MENU_BACKGROUND_URL, STORY_TITLE_LOGO_URL } from "./storyStaticAssets";
import { readStoryPreferences, writeStoryPreferences, type StoryPreferences } from "./storyPreferences";

type StorySettingsProps = { onBack: () => void };

const textSpeedOptions = [
  { value: "slow", label: "慢" },
  { value: "normal", label: "标准" },
  { value: "fast", label: "快" },
] as const satisfies readonly { value: StoryPreferences["textSpeed"]; label: string }[];

const motionOptions = [
  { value: "reduced", label: "轻" },
  { value: "standard", label: "标准" },
  { value: "cinematic", label: "电影感" },
] as const satisfies readonly { value: StoryPreferences["motionIntensity"]; label: string }[];

const volumeFields = [
  { key: "voiceVolume", label: "语音", icon: <SpeakerHigh className="h-4 w-4" weight="bold" /> },
  { key: "musicVolume", label: "音乐", icon: <MusicNotes className="h-4 w-4" weight="bold" /> },
  { key: "ambienceVolume", label: "环境音", icon: <Waveform className="h-4 w-4" weight="bold" /> },
  { key: "effectsVolume", label: "界面音效", icon: <SlidersHorizontal className="h-4 w-4" weight="bold" /> },
] as const;

const transition = { duration: 0.28, ease: "easeOut" } as const;

/** Renders persistent Story presentation settings in the launcher's visual language. */
export function StorySettings({ onBack }: StorySettingsProps) {
  const [settings, setSettings] = useState<StoryPreferences>(readStoryPreferences);
  const reducedMotion = useReducedMotion() ?? false;
  const reduceEffects = reducedMotion || settings.reducedMotion;

  function update<K extends keyof StoryPreferences>(key: K, value: StoryPreferences[K]): void {
    setSettings((current) => {
      const next = { ...current, [key]: value };
      writeStoryPreferences(next);
      return next;
    });
  }

  return (
    <section className="relative h-full min-h-0 overflow-hidden bg-[#1D1520] text-[#4A2738]" data-testid="story-settings">
      <motion.div
        className="absolute inset-0 bg-cover bg-center bg-no-repeat"
        data-testid="story-settings-backdrop"
        initial={{ opacity: 0, scale: reduceEffects ? 1 : 1.06 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: reduceEffects ? 0 : 1.4, ease: "easeOut" }}
        style={{ backgroundImage: `url(${STORY_MENU_BACKGROUND_URL})` }}
      />
      <div aria-hidden="true" className="absolute inset-0 bg-[#281421]/42" />
      <div aria-hidden="true" className="absolute inset-0 bg-[linear-gradient(120deg,rgba(40,20,33,0.2),rgba(40,20,33,0.05)_52%,rgba(104,31,68,0.22))]" />

      <motion.header
        className="absolute left-[clamp(12px,2vw,28px)] top-[clamp(12px,2vh,28px)] z-10 w-[min(18rem,calc(100vw-24px))]"
        initial={{ opacity: 0, y: reduceEffects ? 0 : 18 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: reduceEffects ? 0 : 0.18, duration: reduceEffects ? 0 : 0.6, ease: "easeOut" }}
      >
        <img className="block w-full" src={STORY_TITLE_LOGO_URL} alt="栞 / SHIORI" />
      </motion.header>

      <motion.main
        className="relative z-10 flex h-full min-h-0 flex-col overflow-y-auto pt-[clamp(76px,10vh,104px)]"
        initial={{ opacity: 0, x: reduceEffects ? 0 : 28 }}
        animate={{ opacity: 1, x: 0 }}
        transition={transition}
      >
        <section className="flex min-h-full w-full flex-col border-y border-[#DDA9BE]/75 bg-[#FFF8FC]/90 shadow-[0_18px_48px_rgba(49,17,35,0.3)] backdrop-blur-md" data-testid="story-settings-panel">
          <header className="flex items-center gap-4 border-b border-[#DDA9BE]/65 px-[clamp(18px,4vw,40px)] py-5">
            <button className="grid h-9 w-9 shrink-0 place-items-center rounded-md border border-[#C785A0]/55 bg-[#FFF8FC]/55 text-[#8F355C] transition-colors hover:border-[#B64B75] hover:bg-white hover:text-[#7A2356] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#E5A9C0]" type="button" aria-label="返回剧情主菜单" title="返回剧情主菜单" onClick={onBack}>
              <ArrowLeft className="h-5 w-5" weight="bold" />
            </button>
            <div className="min-w-0 flex-1">
              <p className="m-0 text-[0.68rem] font-semibold uppercase tracking-[0.24em] text-[#B64B75]">Settings</p>
              <h1 className="m-0 mt-1 font-serif text-2xl font-semibold italic text-[#7A2356]">设置</h1>
            </div>
            <span className="flex shrink-0 items-center gap-1.5 text-xs text-[#7D6470]" aria-live="polite">
              <Check className="h-4 w-4 text-[#9A3D63]" weight="bold" />
              已保存
            </span>
          </header>

          <div className="grid gap-8 px-[clamp(18px,4vw,40px)] py-7 lg:grid-cols-2 lg:gap-10">
            <section className="grid content-start gap-5" aria-labelledby="story-settings-presentation">
              <div className="flex items-center gap-2 border-b border-[#DDA9BE]/65 pb-3">
                <SlidersHorizontal className="h-5 w-5 text-[#B64B75]" weight="duotone" />
                <h2 className="m-0 font-serif text-xl font-semibold italic text-[#7A2356]" id="story-settings-presentation">演出</h2>
              </div>
              <div className="grid gap-4">
                <div className="grid gap-2 border-b border-[#DDA9BE]/55 pb-4">
                  <div className="flex items-center justify-between gap-4 text-sm">
                    <span className="font-medium text-[#5E2841]">文字速度</span>
                    <span className="text-xs text-[#8B6676]">{settings.textSpeed === "slow" ? "慢" : settings.textSpeed === "fast" ? "快" : "标准"}</span>
                  </div>
                  <StorySegmentedControl value={settings.textSpeed} options={textSpeedOptions} ariaLabel="文字速度" onChange={(value) => update("textSpeed", value)} />
                </div>
                <div className="flex items-center justify-between gap-4 border-b border-[#DDA9BE]/55 pb-4 text-sm">
                  <div>
                    <p className="m-0 font-medium text-[#5E2841]">立即显示全文</p>
                    <p className="m-0 mt-1 text-xs text-[#8B6676]">跳过逐字显示</p>
                  </div>
                  <span className="flex items-center gap-3 text-xs text-[#8B6676]">{settings.showFullText ? "开启" : "关闭"}<StoryToggle checked={settings.showFullText} label="立即显示全文" onChange={(value) => update("showFullText", value)} /></span>
                </div>
                <div className="grid gap-2 border-b border-[#DDA9BE]/55 pb-4">
                  <div className="flex items-center justify-between gap-4 text-sm">
                    <span className="font-medium text-[#5E2841]">动效强度</span>
                    <span className="text-xs text-[#8B6676]">{settings.motionIntensity === "reduced" ? "轻" : settings.motionIntensity === "cinematic" ? "电影感" : "标准"}</span>
                  </div>
                  <StorySegmentedControl value={settings.motionIntensity} options={motionOptions} ariaLabel="动效强度" onChange={(value) => update("motionIntensity", value)} />
                </div>
                <div className="flex items-center justify-between gap-4 text-sm">
                  <div>
                    <p className="m-0 font-medium text-[#5E2841]">减少动态效果</p>
                    <p className="m-0 mt-1 text-xs text-[#8B6676]">降低页面切换动效</p>
                  </div>
                  <span className="flex items-center gap-3 text-xs text-[#8B6676]">{settings.reducedMotion ? "开启" : "关闭"}<StoryToggle checked={settings.reducedMotion} label="减少动态效果" onChange={(value) => update("reducedMotion", value)} /></span>
                </div>
              </div>
            </section>

            <section className="grid content-start gap-5 lg:border-l lg:border-[#DDA9BE]/65 lg:pl-10" aria-labelledby="story-settings-volume">
              <div className="flex items-center gap-2 border-b border-[#DDA9BE]/65 pb-3">
                <SpeakerHigh className="h-5 w-5 text-[#B64B75]" weight="duotone" />
                <h2 className="m-0 font-serif text-xl font-semibold italic text-[#7A2356]" id="story-settings-volume">音量</h2>
              </div>
              <div>
                {volumeFields.map(({ key, label, icon }) => (
                  <StoryVolumeControl key={key} id={`story-${key}`} label={label} icon={icon} value={settings[key]} onChange={(value) => update(key, value)} />
                ))}
              </div>
            </section>
          </div>
        </section>
      </motion.main>
    </section>
  );
}
