import { useState } from "react";
import { Eye, EyeSlash } from "@phosphor-icons/react";
import { compactPressableClass, cx, settingsInputClass } from "@yinfengwindy/shiori-sdk";
import { parseCompleteSettingsNumber } from "./settingsSectionUtils";

/** Shared icon-only action styling for compact settings controls. */
export const settingsIconButtonClass = cx(compactPressableClass, "grid h-8 w-8 shrink-0 place-items-center rounded-md text-ink-muted hover:bg-surface-hover hover:text-ink");

/** Renders a password input whose value can be revealed locally. */
export function SettingsSecretInput({
  value,
  onChange,
  ariaLabel,
  autoFocus,
  onBlur,
}: {
  value: string;
  onChange: (value: string) => void;
  ariaLabel?: string;
  autoFocus?: boolean;
  onBlur?: () => void;
}) {
  const [visible, setVisible] = useState(false);
  return (
    <div className="flex items-center gap-2">
      <input aria-label={ariaLabel} className={cx(settingsInputClass, "min-w-0 flex-1")} type={visible ? "text" : "password"} autoComplete="off" spellCheck={false} autoFocus={autoFocus} value={value} onBlur={onBlur} onChange={(event) => onChange(event.target.value)} />
      <button
        className={settingsIconButtonClass}
        type="button"
        onClick={() => setVisible((current) => !current)}
        aria-label={visible ? "隐藏密钥" : "显示密钥"}
        title={visible ? "隐藏密钥" : "显示密钥"}
      >
        {visible ? <EyeSlash className="h-3.5 w-3.5" weight="bold" /> : <Eye className="h-3.5 w-3.5" weight="bold" />}
      </button>
    </div>
  );
}

/**
 * Numeric settings input with an optional unit suffix. The typed text is kept
 * locally, so an empty box or intermediate forms such as `0.` stay editable;
 * only complete numbers (`parseCompleteSettingsNumber`) are reported, and
 * leaving the box with anything else restores the current value. An external
 * value change replaces the text.
 */
export function SettingsNumberInput({
  value,
  onChange,
  unit,
  ariaLabel,
  min,
  max,
}: {
  value: number;
  onChange: (value: number) => void;
  unit?: string;
  ariaLabel: string;
  min?: number;
  max?: number;
}) {
  const [text, setText] = useState(() => String(value));
  const [reported, setReported] = useState(value);
  if (!Object.is(value, reported)) {
    // Adopt values replaced from outside (load, reset) without an effect round-trip.
    setReported(value);
    setText(String(value));
  }
  return (
    <div className="relative flex items-center">
      <input
        aria-label={ariaLabel}
        className={cx(settingsInputClass, "tabular-nums", unit && "pr-14")}
        inputMode="decimal"
        // A textbox cannot carry aria-value*; the accepted range is a hover hint and the backend validates.
        title={min !== undefined || max !== undefined ? `${min ?? "…"} – ${max ?? "…"}` : undefined}
        value={text}
        onChange={(event) => {
          setText(event.target.value);
          const next = parseCompleteSettingsNumber(event.target.value);
          if (next === null || Object.is(next, value)) return;
          setReported(next);
          onChange(next);
        }}
        onBlur={() => {
          if (parseCompleteSettingsNumber(text) === null) setText(String(value));
        }}
      />
      {unit ? <span className="pointer-events-none absolute right-3 text-caption text-ink-muted" aria-hidden="true">{unit}</span> : null}
    </div>
  );
}

