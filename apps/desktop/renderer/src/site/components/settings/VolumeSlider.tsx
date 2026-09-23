import type { CSSProperties } from "react";

interface VolumeSliderProps {
  id: string;
  label: string;
  value: number;
  onChange: (value: number) => void;
}

/** Labelled 0–100 range input with its value shown alongside. */
export function VolumeSlider({ id, label, value, onChange }: VolumeSliderProps) {
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-baseline justify-between">
        <label htmlFor={id} className="text-body text-site-ink">
          {label}
        </label>
        <span className="site-settings-value text-body-sm tabular-nums" aria-hidden="true">
          {value}
        </span>
      </div>
      <input
        id={id}
        type="range"
        min={0}
        max={100}
        step={1}
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
        className="site-range w-full"
        style={{ "--site-range-fill": `${value}%` } as CSSProperties}
      />
    </div>
  );
}
