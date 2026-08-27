import type { ReactNode } from "react";

/** One value-label pair accepted by a Story segmented preference control. */
export type StorySettingOption<T extends string> = {
  value: T;
  label: string;
};

type StorySegmentedControlProps<T extends string> = {
  value: T;
  options: readonly StorySettingOption<T>[];
  ariaLabel: string;
  onChange: (value: T) => void;
};

type StoryToggleProps = {
  checked: boolean;
  label: string;
  onChange: (checked: boolean) => void;
};

type StoryVolumeControlProps = {
  id: string;
  label: string;
  icon: ReactNode;
  value: number;
  onChange: (value: number) => void;
};

/** Renders a compact option group with one clearly selected Story mode. */
export function StorySegmentedControl<T extends string>({ value, options, ariaLabel, onChange }: StorySegmentedControlProps<T>) {
  return (
    <div className="grid grid-cols-3 overflow-hidden rounded-md border border-[#D9A5B9]/80 bg-[#FFF8FC]/65 p-1" aria-label={ariaLabel} role="group">
      {options.map((option) => {
        const selected = option.value === value;
        return (
          <button
            key={option.value}
            className={selected
              ? "min-h-9 rounded-[3px] bg-[#7A2356] px-3 py-1.5 text-xs font-semibold text-white shadow-[0_4px_12px_rgba(93,21,51,0.18)] transition-colors"
              : "min-h-9 rounded-[3px] px-3 py-1.5 text-xs font-medium text-[#7A2356]/70 transition-colors hover:bg-white/80 hover:text-[#7A2356]"}
            type="button"
            aria-pressed={selected}
            onClick={() => onChange(option.value)}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}

/** Renders an accessible Story preference switch with an explicit state label. */
export function StoryToggle({ checked, label, onChange }: StoryToggleProps) {
  return (
    <button
      className={`relative inline-flex h-6 w-11 shrink-0 appearance-none rounded-full border-0 p-0 transition-colors duration-200 focus:outline-none focus-visible:ring-2 focus-visible:ring-[#C65B85]/35 focus-visible:ring-offset-2 focus-visible:ring-offset-[#FFF8FC] ${checked ? "bg-[#7A2356]" : "bg-[#D7B8C4]"}`}
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      onClick={() => onChange(!checked)}
    >
      <span
        className={`absolute left-0.5 top-0.5 h-5 w-5 rounded-full bg-white shadow-[0_2px_6px_rgba(93,21,51,0.2)] transition-transform duration-200 ${checked ? "translate-x-5" : "translate-x-0"}`}
        aria-hidden="true"
      />
    </button>
  );
}

/** Renders one labeled volume slider with a visible numeric value. */
export function StoryVolumeControl({ id, label, icon, value, onChange }: StoryVolumeControlProps) {
  return (
    <label className="grid grid-cols-[minmax(0,1fr)_minmax(9rem,1.4fr)_3rem] items-center gap-3 border-b border-[#DDA9BE]/55 py-3.5 text-sm last:border-b-0" htmlFor={id}>
      <span className="flex min-w-0 items-center gap-2 text-[#5E2841]">
        <span className="grid h-7 w-7 shrink-0 place-items-center rounded-md bg-[#F6DCE7] text-[#9A3D63]">{icon}</span>
        <span className="truncate">{label}</span>
      </span>
      <input
        className="h-1.5 w-full cursor-pointer appearance-none rounded-full accent-[#7A2356] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#C65B85]/35 focus-visible:ring-offset-4 focus-visible:ring-offset-[#FFF8FC]"
        id={id}
        type="range"
        min="0"
        max="100"
        value={value}
        aria-label={label}
        onChange={(event) => onChange(Number(event.target.value))}
        style={{ background: `linear-gradient(90deg, #7A2356 ${value}%, rgba(122, 35, 86, 0.16) ${value}%)` }}
      />
      <output className="text-right text-xs font-semibold tabular-nums text-[#8B6676]" htmlFor={id}>
        {value}%
      </output>
    </label>
  );
}
