import { ArrowLeft } from "@phosphor-icons/react";
import { useState } from "react";
import { readStoryPreferences, writeStoryPreferences, type StoryPreferences } from "./storyPreferences";

type StorySettingsProps = { onBack: () => void };

const volumeFields: Array<{ key: "voiceVolume" | "musicVolume" | "ambienceVolume" | "effectsVolume"; label: string }> = [
  { key: "voiceVolume", label: "语音" },
  { key: "musicVolume", label: "音乐" },
  { key: "ambienceVolume", label: "环境音" },
  { key: "effectsVolume", label: "界面音效" },
];

/** Renders persistent Story presentation settings. */
export function StorySettings({ onBack }: StorySettingsProps) {
  const [settings, setSettings] = useState<StoryPreferences>(readStoryPreferences);

  function update<K extends keyof StoryPreferences>(key: K, value: StoryPreferences[K]): void {
    setSettings((current) => {
      const next = { ...current, [key]: value };
      writeStoryPreferences(next);
      return next;
    });
  }

  return (
    <section className="h-full min-h-0 overflow-y-auto bg-[#111512] text-[#F6F0E8]" data-testid="story-settings">
      <div className="mx-auto max-w-2xl px-8 py-10">
        <header className="flex items-center gap-4 border-b border-white/10 pb-6"><button className="grid h-9 w-9 place-items-center rounded-md text-white/65 hover:bg-white/10 hover:text-white" type="button" aria-label="返回剧情主菜单" title="返回剧情主菜单" onClick={onBack}><ArrowLeft /></button><div><p className="m-0 text-xs uppercase tracking-[0.24em] text-[#D49A76]">Story</p><h1 className="m-0 mt-2 font-serif text-3xl">设置</h1></div></header>
        <div className="grid gap-8 py-8">
          <section className="grid gap-4"><h2 className="m-0 font-serif text-xl">演出</h2><label className="flex items-center justify-between gap-4 border-b border-white/10 pb-4 text-sm"><span>文字速度</span><select className="rounded-md border border-white/15 bg-white/5 px-3 py-2 text-sm text-white focus:border-[#D49A76] focus:outline-none" value={settings.textSpeed} onChange={(event) => update("textSpeed", event.target.value as StoryPreferences["textSpeed"])}><option value="slow">慢</option><option value="normal">标准</option><option value="fast">快</option></select></label><label className="flex items-center justify-between gap-4 border-b border-white/10 pb-4 text-sm"><span>立即显示全文</span><input className="h-4 w-4 accent-[#C98B65]" type="checkbox" checked={settings.showFullText} onChange={(event) => update("showFullText", event.target.checked)} /></label><label className="flex items-center justify-between gap-4 border-b border-white/10 pb-4 text-sm"><span>动效强度</span><select className="rounded-md border border-white/15 bg-white/5 px-3 py-2 text-sm text-white focus:border-[#D49A76] focus:outline-none" value={settings.motionIntensity} onChange={(event) => update("motionIntensity", event.target.value as StoryPreferences["motionIntensity"])}><option value="reduced">轻</option><option value="standard">标准</option><option value="cinematic">电影感</option></select></label><label className="flex items-center justify-between gap-4 text-sm"><span>减少动态效果</span><input className="h-4 w-4 accent-[#C98B65]" type="checkbox" checked={settings.reducedMotion} onChange={(event) => update("reducedMotion", event.target.checked)} /></label></section>
          <section className="grid gap-4"><h2 className="m-0 font-serif text-xl">音量</h2>{volumeFields.map(({ key, label }) => <label key={key} className="grid grid-cols-[90px_1fr_44px] items-center gap-4 text-sm"><span>{label}</span><input className="accent-[#C98B65]" type="range" min="0" max="100" value={settings[key]} onChange={(event) => update(key, Number(event.target.value))} /><output className="text-right text-white/55">{settings[key]}</output></label>)}</section>
        </div>
      </div>
    </section>
  );
}
