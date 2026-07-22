import { ArrowLeft, GlobeHemisphereEast } from "@phosphor-icons/react";
import type React from "react";

type WorldAppSurfaceProps = {
  children: React.ReactNode;
  onExit: () => void;
};

/** Top-level world application surface, deliberately separate from the desktop chat shell. */
export function WorldAppSurface({ children, onExit }: WorldAppSurfaceProps) {
  return (
    <section className="grid h-screen min-h-0 grid-rows-[48px_minmax(0,1fr)] bg-[#F8F8F6] text-[#242625]" data-testid="world-app-surface">
      <header className="flex items-center border-b border-[#DDE2DF] bg-white px-3">
        <button className="grid h-8 w-8 place-items-center rounded-md text-[#59615C] hover:bg-[#F0F3F0]" type="button" aria-label="返回 Shiori" title="返回 Shiori" onClick={onExit}><ArrowLeft /></button>
        <div className="ml-3 flex items-center gap-2 font-serif text-sm font-semibold"><GlobeHemisphereEast className="text-[#A75F41]" weight="duotone" />世界</div>
      </header>
      <div className="min-h-0">{children}</div>
    </section>
  );
}
