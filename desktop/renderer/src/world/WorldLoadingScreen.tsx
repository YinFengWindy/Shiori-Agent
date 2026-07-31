import { ArrowLeft, ArrowClockwise, GlobeHemisphereEast } from "@phosphor-icons/react";
import { resolveWorldLoadingPresentation } from "./worldLoadingPolicy";

type WorldLoadingScreenProps = {
  mode: "listing" | "world";
  busy?: boolean;
  error?: string;
  elapsedMs?: number;
  loaded?: number;
  total?: number;
  onRetry?: () => void;
  onBack?: () => void;
};

const stages = ["读取世界", "恢复演出", "准备舞台"];

/** Renders the World entry and save-loading transition without a spinner. */
export function WorldLoadingScreen({ mode, busy = true, error = "", elapsedMs = 250, loaded = 0, total = 0, onRetry, onBack }: WorldLoadingScreenProps) {
  const activeStage = mode === "listing" ? 0 : 1;
  const presentation = resolveWorldLoadingPresentation({ elapsedMs, loaded, total });
  return (
    <section className="relative grid h-full min-h-0 place-items-center overflow-hidden text-[#F6F0E8]" data-testid="world-loading-screen" aria-busy={busy}>
      {/* Full-screen background */}
      <div className="absolute inset-0 bg-cover bg-center bg-no-repeat" style={{ backgroundImage: "url('/assets/backgrounds/default-galgame-bg.png')" }} />
      <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" />
      <div className="relative z-10 w-[min(520px,calc(100%-48px))]">
        <div className="flex items-center gap-2 text-xs uppercase tracking-[0.28em] text-[#D49A76]"><GlobeHemisphereEast weight="duotone" />World</div>
        <h1 className="mt-5 font-serif text-3xl text-[#F7EBDD]">正在打开世界</h1>
        <p className="mt-2 text-sm text-white/50">请稍候，舞台正在恢复。</p>
        <div className="mt-12 grid gap-4" aria-label="世界加载阶段">
          {stages.map((stage, index) => <div key={stage} className="grid grid-cols-[20px_1fr_auto] items-center gap-3"><span className={`h-2 w-2 rounded-full ${index <= activeStage ? "bg-[#E5A17B]" : "bg-white/20"}`} /><span className={index <= activeStage ? "text-sm text-white/90" : "text-sm text-white/35"}>{stage}</span><span className="text-xs text-white/35">{index < activeStage ? "完成" : index === activeStage ? "进行中" : "等待"}</span></div>)}
        </div>
        {presentation.kind === "progress" ? <div className="mt-8"><div className="h-1 overflow-hidden bg-white/10" role="progressbar" aria-valuemin={0} aria-valuemax={presentation.total || 1} aria-valuenow={presentation.loaded}><div className="h-full bg-[#C98B65] transition-[width] duration-300" style={{ width: `${presentation.ratio * 100}%` }} /></div><p className="m-0 mt-3 text-xs text-white/45">{presentation.loaded} / {presentation.total}</p></div> : null}
        {error ? <div className="mt-7 border border-[#A95F4D] bg-[#3A201C] px-3 py-3 text-sm text-[#FFD8CD]" role="alert">{error}</div> : null}
        {(error && onRetry) || onBack ? <div className="mt-6 flex items-center gap-3">{error && onRetry ? <button className="inline-flex h-10 items-center gap-2 rounded-md bg-[#B86F4D] px-4 text-sm text-white hover:bg-[#CC805C]" type="button" onClick={onRetry}><ArrowClockwise />重试</button> : null}{onBack ? <button className="inline-flex h-10 items-center gap-2 rounded-md px-3 text-sm text-white/60 hover:text-white" type="button" onClick={onBack}><ArrowLeft />返回</button> : null}</div> : null}
      </div>
    </section>
  );
}
