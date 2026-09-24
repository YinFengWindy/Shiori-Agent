import { ArrowsClockwise, ImageSquare, X } from "@phosphor-icons/react";
import { toFileUrl } from "../../../apps/desktop/renderer/src/shared/format";
import { compactPressableClass, cx, pressableClass } from "../../../apps/desktop/renderer/src/shared/styles";
import type { ImageStudioFormState } from "./types";

type BaseImageFieldProps = {
  form: Pick<ImageStudioFormState, "baseImagePath" | "strength" | "noise">;
  onPick: () => void;
  onChange: (next: Partial<ImageStudioFormState>) => void;
};

const overlayButtonClass = cx(
  compactPressableClass,
  "grid h-7 w-7 place-items-center rounded-md surface-glass text-ink-secondary hover:bg-white hover:text-ink",
);

function formatSliderValue(value: number): string {
  return value.toFixed(2).replace(/\.?0+$/, "");
}

function Slider({ label, value, min, max, onChange }: { label: string; value: number; min: number; max: number; onChange: (value: number) => void }) {
  return (
    <label className="grid gap-1">
      <span className="flex items-center justify-between text-caption text-ink-secondary">
        <span>{label}</span>
        <span className="tabular-nums text-ink-muted">{formatSliderValue(value)}</span>
      </span>
      <input
        className="w-full accent-accent"
        type="range"
        min={min}
        max={max}
        step="0.01"
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
      />
    </label>
  );
}

/** Optional reference image for img2img: an add button, or the picked image with its strength/noise. */
export function BaseImageField({ form, onPick, onChange }: BaseImageFieldProps) {
  if (!form.baseImagePath) {
    return (
      <button
        className={cx(
          pressableClass,
          "flex h-11 w-full items-center gap-2 rounded-md border border-dashed border-line bg-white/60 px-3 text-left text-body-sm text-ink-secondary hover:border-line-accent hover:bg-accent-softer hover:text-accent-text",
        )}
        type="button"
        onClick={onPick}
      >
        <ImageSquare className="h-[18px] w-[18px] shrink-0" aria-hidden="true" />
        <span className="min-w-0 flex-1 truncate">添加参考图</span>
        <span className="shrink-0 text-caption text-ink-muted">可选</span>
      </button>
    );
  }
  return (
    <div className="grid gap-3 rounded-lg border border-line-soft bg-surface p-2.5" data-testid="novelai-base-image">
      <div className="relative overflow-hidden rounded-md bg-surface-soft">
        <img className="block h-36 w-full object-cover" src={toFileUrl(form.baseImagePath)} alt="参考图" />
        <div className="absolute right-1.5 top-1.5 flex gap-1.5">
          <button className={overlayButtonClass} type="button" aria-label="更换参考图" title="更换参考图" onClick={onPick}>
            <ArrowsClockwise className="h-4 w-4" aria-hidden="true" />
          </button>
          <button className={overlayButtonClass} type="button" aria-label="移除参考图" title="移除参考图" onClick={() => onChange({ baseImagePath: "" })}>
            <X className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>
      </div>
      <div className="grid gap-2 px-0.5">
        <Slider label="重绘强度" value={form.strength} min={0.01} max={1} onChange={(strength) => onChange({ strength })} />
        <Slider label="噪声" value={form.noise} min={0} max={0.99} onChange={(noise) => onChange({ noise })} />
      </div>
    </div>
  );
}
