import { ArrowLeft, X } from "@phosphor-icons/react";
import { SceneShot } from "./SceneShot";
import type { SceneBeat } from "./types";

type GalgameFocusModeProps = {
  worldName: string;
  beat: SceneBeat;
  onExit: () => void;
  onRedrawShot: (shotId: string) => void;
};

/** Renders an app-level visual-novel presentation without controlling run lifecycle. */
export function GalgameFocusMode({ worldName, beat, onExit, onRedrawShot }: GalgameFocusModeProps) {
  return (
    <section className="fixed inset-0 z-[100] overflow-hidden bg-[#171A18] text-white" data-testid="galgame-focus-mode">
      {beat.shot ? <SceneShot shot={beat.shot} immersive onRedraw={onRedrawShot} /> : <div className="absolute inset-0 bg-[radial-gradient(circle_at_65%_25%,#647068_0%,#303632_38%,#151816_78%)]" />}
      <div className="pointer-events-none absolute inset-0 bg-gradient-to-t from-black/90 via-transparent to-black/35" />
      <header className="absolute inset-x-0 top-0 z-10 flex items-center justify-between p-5"><span className="font-serif text-sm tracking-normal text-white/75">{worldName}</span><button className="pointer-events-auto grid h-10 w-10 place-items-center rounded-md bg-black/35 text-white backdrop-blur-sm hover:bg-black/55" type="button" aria-label="退出焦点模式" onClick={onExit}><X /></button></header>
      <div className="absolute inset-x-0 bottom-0 z-10 px-[clamp(24px,8vw,120px)] pb-[clamp(28px,7vh,72px)]"><div className="max-w-4xl border-l-2 border-[#E59A70] bg-black/45 px-6 py-5 backdrop-blur-md">{beat.speakerName ? <h1 className="m-0 mb-2 font-serif text-lg font-semibold text-[#F3B18B]">{beat.speakerName}</h1> : null}<p className="m-0 whitespace-pre-wrap font-serif text-lg leading-8 text-white">{beat.content}</p></div><button className="pointer-events-auto mt-3 inline-flex h-9 items-center gap-2 rounded-md bg-black/35 px-3 text-xs text-white/80 hover:bg-black/55" type="button" onClick={onExit}><ArrowLeft />返回工作台</button></div>
    </section>
  );
}
