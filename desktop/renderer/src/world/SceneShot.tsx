import { ArrowClockwise, CaretLeft, CaretRight, ImageSquare } from "@phosphor-icons/react";
import { useMemo, useState } from "react";
import { cx } from "../shared/styles";
import type { SceneShot as SceneShotModel } from "./types";

type SceneShotProps = {
  shot: SceneShotModel;
  redrawing?: boolean;
  immersive?: boolean;
  onRedraw: (shotId: string) => void;
};

/** Renders one asynchronous scene image with retained alternatives. */
export function SceneShot({ shot, redrawing = false, immersive = false, onRedraw }: SceneShotProps) {
  const initialIndex = Math.max(0, shot.assets.findIndex((asset) => asset.id === shot.activeAssetId));
  const [selectedIndex, setSelectedIndex] = useState(initialIndex);
  const selected = shot.assets[selectedIndex] ?? null;
  const developing = shot.status === "developing" || redrawing;
  const label = shot.status === "failed" ? "显影中断" : developing ? "正在显影" : selected?.createdAtLabel ?? "镜头画面";
  const frameClass = immersive ? "h-full w-full" : "aspect-[16/9] w-full";
  const canBrowse = shot.assets.length > 1;
  const selectedNumber = useMemo(() => Math.min(selectedIndex + 1, shot.assets.length), [selectedIndex, shot.assets.length]);

  return (
    <figure className={cx("group relative m-0 overflow-hidden rounded-md bg-[#D9DDD8]", frameClass)} data-testid="scene-shot">
      {selected ? (
        <img className="h-full w-full object-cover transition-opacity duration-700" src={selected.imageUrl} alt={shot.prompt} />
      ) : (
        <div className="relative h-full min-h-44 overflow-hidden bg-[#D9DDD8]" data-testid="scene-shot-developing">
          <div className="absolute inset-0 bg-[linear-gradient(135deg,transparent_18%,rgba(70,78,72,0.28)_19%,transparent_20%,transparent_44%,rgba(70,78,72,0.18)_45%,transparent_46%),radial-gradient(circle_at_70%_30%,rgba(255,255,255,0.8),transparent_32%),linear-gradient(160deg,#EEF0EC_0%,#C4CBC5_48%,#8E9891_100%)] grayscale" />
          <div className="absolute inset-[12%] rounded-[42%_58%_34%_66%/55%_42%_58%_45%] border border-[#6E7771]/45 shadow-[0_0_45px_rgba(255,255,255,0.55)]" />
          <ImageSquare className="absolute left-1/2 top-1/2 h-8 w-8 -translate-x-1/2 -translate-y-1/2 text-[#59635C]/70" weight="thin" />
        </div>
      )}
      <div className="absolute inset-x-0 bottom-0 flex items-end justify-between gap-3 bg-gradient-to-t from-black/65 to-transparent px-3 pb-3 pt-10 text-white">
        <span className="text-xs">{label}</span>
        <div className="flex items-center gap-1">
          {canBrowse ? (
            <>
              <button className="grid h-7 w-7 place-items-center rounded-md bg-black/35" type="button" aria-label="上一幅画面" onClick={() => setSelectedIndex((index) => (index - 1 + shot.assets.length) % shot.assets.length)}><CaretLeft /></button>
              <span className="min-w-8 text-center text-xs">{selectedNumber}/{shot.assets.length}</span>
              <button className="grid h-7 w-7 place-items-center rounded-md bg-black/35" type="button" aria-label="下一幅画面" onClick={() => setSelectedIndex((index) => (index + 1) % shot.assets.length)}><CaretRight /></button>
            </>
          ) : null}
          <button className="grid h-7 w-7 place-items-center rounded-md bg-black/35 disabled:opacity-50" type="button" aria-label="重绘镜头" disabled={redrawing} onClick={() => onRedraw(shot.id)}><ArrowClockwise className={cx(redrawing && "animate-spin")} /></button>
        </div>
      </div>
    </figure>
  );
}
