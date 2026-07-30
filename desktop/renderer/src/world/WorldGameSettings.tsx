import { ArrowLeft } from "@phosphor-icons/react";
import { useState } from "react";
import { readWorldGameSettings, writeWorldGameSettings, type WorldGameSettings } from "./worldGameSettingsStore";

type WorldGameSettingsProps = { onBack: () => void };

const volumeFields: Array<{ key: "voiceVolume" | "musicVolume" | "ambienceVolume" | "effectsVolume"; label: string }> = [
  { key: "voiceVolume", label: "语音" },
  { key: "musicVolume", label: "音乐" },
  { key: "ambienceVolume", label: "环境音" },
  { key: "effectsVolume", label: "界面音效" },
];

/** Renders persistent World-only presentation settings. */
export function WorldGameSettings({ onBack }: WorldGameSettingsProps) {
  const [settings, setSettings] = useState<WorldGameSettings>(readWorldGameSettings);

  function update<K extends keyof WorldGameSettings>(key: K, value: WorldGameSettings[K]): void {
    setSettings((current) => {
      const next = { ...current, [key]: value };
      writeWorldGameSettings(next);
      return next;
    });
  }

  return (
    <section className="h-full min-h-0 overflow-y-auto bg-[#111512] text-[#F6F0E8]" data-testid="world-game-settings">
      <div className="mx-auto max-w-2xl px-8 py-10">
        <header className="flex items-center gap-4 border-b border-white/10 pb-6"><button className="grid h-9 w-9 place-items-center rounded-md text-white/65 hover:bg-white/10 hover:text-white" type="button" aria-label="返回 World 主菜单" title="返回 World 主菜单" onClick={onBack}><ArrowLeft /></button><div><p className="m-0 text-xs uppercase tracking-[0.24em] text-[#D49A76]">World</p><h1 className="m-0 mt-2 font-serif text-3xl">设置</h1></div></header>
        <div className="grid gap-8 py-8">
          <section className="grid gap-4"><h2 className="m-0 font-serif text-xl">演出</h2><label className="flex items-center justify-between gap-4 border-b border-white/10 pb-4 text-sm"><span>文字速度</span><select className="rounded-md border border-white/15 bg-white/5 px-3 py-2 text-sm text-white focus:border-[#D49A76] focus:outline-none" value={settings.textSpeed} onChange={(event) => update("textSpeed", event.target.value as WorldGameSettings["textSpeed"])}><option value="slow">慢</option><option value="normal">标准</option><option value="fast">快</option></select></label><label className="flex items-center justify-between gap-4 border-b border-white/10 pb-4 text-sm"><span>立即显示全文</span><input className="h-4 w-4 accent-[#C98B65]" type="checkbox" checked={settings.showFullText} onChange={(event) => update("showFullText", event.target.checked)} /></label><label className="flex items-center justify-between gap-4 border-b border-white/10 pb-4 text-sm"><span>自动播放</span><input className="h-4 w-4 accent-[#C98B65]" type="checkbox" checked={settings.autoPlay} onChange={(event) => update("autoPlay", event.target.checked)} /></label><label className="grid grid-cols-[1fr_180px_48px] items-center gap-4 border-b border-white/10 pb-4 text-sm"><span>自动播放间隔</span><input className="accent-[#C98B65]" type="range" min="300" max="5000" step="100" value={settings.autoPlayDelayMs} onChange={(event) => update("autoPlayDelayMs", Number(event.target.value))} /><output className="text-right text-white/55">{(settings.autoPlayDelayMs / 1000).toFixed(1)}s</output></label><label className="flex items-center justify-between gap-4 border-b border-white/10 pb-4 text-sm"><span>快进范围</span><select className="rounded-md border border-white/15 bg-white/5 px-3 py-2 text-sm text-white focus:border-[#D49A76] focus:outline-none" value={settings.skipReadTextOnly ? "read" : "all"} onChange={(event) => update("skipReadTextOnly", event.target.value === "read")}><option value="read">仅已读文本</option><option value="all">全部文本</option></select></label><label className="flex items-center justify-between gap-4 border-b border-white/10 pb-4 text-sm"><span>动效强度</span><select className="rounded-md border border-white/15 bg-white/5 px-3 py-2 text-sm text-white focus:border-[#D49A76] focus:outline-none" value={settings.motionIntensity} onChange={(event) => update("motionIntensity", event.target.value as WorldGameSettings["motionIntensity"])}><option value="reduced">轻</option><option value="standard">标准</option><option value="cinematic">电影感</option></select></label><label className="flex items-center justify-between gap-4 text-sm"><span>减少动态效果</span><input className="h-4 w-4 accent-[#C98B65]" type="checkbox" checked={settings.reducedMotion} onChange={(event) => update("reducedMotion", event.target.checked)} /></label></section>
          <section className="grid gap-4"><h2 className="m-0 font-serif text-xl">音量</h2>{volumeFields.map(({ key, label }) => <label key={key} className="grid grid-cols-[90px_1fr_44px] items-center gap-4 text-sm"><span>{label}</span><input className="accent-[#C98B65]" type="range" min="0" max="100" value={settings[key]} onChange={(event) => update(key, Number(event.target.value))} /><output className="text-right text-white/55">{settings[key]}</output></label>)}</section>
        </div>
      </div>
    </section>
  );
}
