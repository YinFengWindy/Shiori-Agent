import { ArrowLeft, ArrowClockwise, GlobeHemisphereEast } from "@phosphor-icons/react";

type WorldLoadingScreenProps = {
  mode: "listing" | "world";
  busy?: boolean;
  error?: string;
  onRetry?: () => void;
  onBack?: () => void;
};

const stages = ["读取世界", "恢复演出", "准备舞台"];

/** Renders the World entry and save-loading transition without a spinner. */
export function WorldLoadingScreen({ mode, busy = true, error = "", onRetry, onBack }: WorldLoadingScreenProps) {
  const activeStage = mode === "listing" ? 0 : 1;
  return (
    <section className="relative grid h-full min-h-0 place-items-center overflow-hidden bg-[#111512] text-[#F6F0E8]" data-testid="world-loading-screen" aria-busy={busy}>
      <div className="absolute inset-0 opacity-40" aria-hidden="true"><div className="absolute left-[18%] top-[26%] h-px w-[64%] bg-[#C98B65]/30" /><div className="absolute left-[31%] top-[27%] h-24 w-px bg-[#C98B65]/20" /><div className="absolute right-[26%] bottom-[28%] h-px w-[32%] bg-white/15" /></div>
      <div className="relative w-[min(520px,calc(100%-48px))]">
        <div className="flex items-center gap-2 text-xs uppercase tracking-[0.28em] text-[#D49A76]"><GlobeHemisphereEast weight="duotone" />World</div>
        <h1 className="mt-5 font-serif text-3xl text-[#F7EBDD]">正在打开世界</h1>
        <p className="mt-2 text-sm text-white/50">请稍候，舞台正在恢复。</p>
        <div className="mt-12 grid gap-4" aria-label="世界加载阶段">
          {stages.map((stage, index) => <div key={stage} className="grid grid-cols-[20px_1fr_auto] items-center gap-3"><span className={`h-2 w-2 rounded-full ${index <= activeStage ? "bg-[#E5A17B]" : "bg-white/20"}`} /><span className={index <= activeStage ? "text-sm text-white/90" : "text-sm text-white/35"}>{stage}</span><span className="text-xs text-white/35">{index < activeStage ? "完成" : index === activeStage ? "进行中" : "等待"}</span></div>)}
        </div>
        <div className="relative mt-8 h-px overflow-hidden bg-white/10"><div className="absolute inset-y-0 left-0 w-2/3 bg-[#C98B65] motion-safe:animate-pulse" /></div>
        {error ? <div className="mt-7 border border-[#A95F4D] bg-[#3A201C] px-3 py-3 text-sm text-[#FFD8CD]" role="alert">{error}</div> : null}
        {(error && onRetry) || onBack ? <div className="mt-6 flex items-center gap-3">{error && onRetry ? <button className="inline-flex h-10 items-center gap-2 rounded-md bg-[#B86F4D] px-4 text-sm text-white hover:bg-[#CC805C]" type="button" onClick={onRetry}><ArrowClockwise />重试</button> : null}{onBack ? <button className="inline-flex h-10 items-center gap-2 rounded-md px-3 text-sm text-white/60 hover:text-white" type="button" onClick={onBack}><ArrowLeft />返回</button> : null}</div> : null}
      </div>
    </section>
  );
}
