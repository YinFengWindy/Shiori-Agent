import { cx } from "@yinfengwindy/shiori-sdk";
import { storySegmentOptionClass, storySegmentTrackClass } from "./storyStyles";

/** One value-label pair accepted by a Story segmented preference control. */
export type StorySettingOption<T extends string> = {
  value: T;
  label: string;
};

type StorySegmentedControlProps<T extends string> = {
  value: T;
  options: readonly StorySettingOption<T>[];
  ariaLabel: string;
  disabled?: boolean;
  onChange: (value: T) => void;
};

type StoryToggleProps = {
  checked: boolean;
  label: string;
  onChange: (checked: boolean) => void;
};

/** Renders a compact option group with one clearly selected Story mode. */
export function StorySegmentedControl<T extends string>({ value, options, ariaLabel, disabled = false, onChange }: StorySegmentedControlProps<T>) {
  return (
    <div className={cx(storySegmentTrackClass, "grid-cols-3", disabled && "opacity-45")} aria-label={ariaLabel} role="group">
      {options.map((option) => (
        <button key={option.value} className={storySegmentOptionClass(option.value === value)} type="button" aria-pressed={option.value === value} disabled={disabled} onClick={() => onChange(option.value)}>
          {option.label}
        </button>
      ))}
    </div>
  );
}

/** Renders an accessible Story preference switch. */
export function StoryToggle({ checked, label, onChange }: StoryToggleProps) {
  return (
    <button
      className={cx("relative inline-flex h-6 w-11 shrink-0 appearance-none rounded-full border-0 p-0 transition-colors duration-base", checked ? "bg-[color:var(--story-wine)]" : "bg-[color:var(--story-line-field)]")}
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      onClick={() => onChange(!checked)}
    >
      <span className={cx("absolute left-0.5 top-0.5 h-5 w-5 rounded-full bg-[color:var(--story-on-wine)] shadow-[var(--story-shadow-selected)] transition-transform duration-base", checked ? "translate-x-5" : "translate-x-0")} aria-hidden="true" />
    </button>
  );
}

type StoryVolumeControlProps = {
  id: string;
  label: string;
  value: number;
  disabled?: boolean;
  onChange: (value: number) => void;
};

/** Renders one labeled volume slider with its numeric value. */
export function StoryVolumeControl({ id, label, value, disabled = false, onChange }: StoryVolumeControlProps) {
  return (
    <span className={cx("grid grid-cols-[minmax(0,1fr)_3rem] items-center gap-3", disabled && "opacity-45")}>
      <input
        className="h-1.5 w-full cursor-pointer appearance-none rounded-full accent-[color:var(--story-wine)] disabled:cursor-default"
        id={id}
        type="range"
        min="0"
        max="100"
        value={value}
        disabled={disabled}
        aria-label={label}
        onChange={(event) => onChange(Number(event.target.value))}
        style={{ background: `linear-gradient(90deg, var(--story-wine) ${value}%, var(--story-line-field) ${value}%)` }}
      />
      <output className="text-right text-xs font-semibold tabular-nums text-[color:var(--story-ink-muted)]" htmlFor={id}>{value}%</output>
    </span>
  );
}
