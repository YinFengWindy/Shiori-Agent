import { useState } from "react";
import { cx, inputClass } from "@yinfengwindy/shiori-sdk";

/** The accepted range of an `IntegerField`; `optional` lets blank text mean null. */
export type IntegerRange = { min: number; max?: number; optional?: boolean };

/** The whole number `text` stands for within `range`; null for accepted blank text; undefined when invalid. */
export function parseInteger(text: string, { min, max, optional = false }: IntegerRange) {
  const trimmed = text.trim();
  if (trimmed === "") return optional ? null : undefined;
  if (!/^\d+$/.test(trimmed)) return undefined;
  const value = Number(trimmed);
  return value >= min && (max === undefined || value <= max) ? value : undefined;
}

type IntegerFieldProps = IntegerRange & {
  label: string;
  value: number | null;
  disabled: boolean;
  onChange(value: number | null): void;
};

/**
 * A whole-number setting. Valid text moves the draft; invalid text is marked
 * and never written. Typed text stays shown only while it still belongs to
 * the stored value it was typed against, so a reload or a normalised save
 * shows the stored value.
 */
export function IntegerField({ label, value, disabled, onChange, ...range }: IntegerFieldProps) {
  const [typed, setTyped] = useState<{ text: string; value: number | null } | null>(null);
  const text = typed && typed.value === value ? typed.text : value === null ? "" : String(value);
  const invalid = parseInteger(text, range) === undefined;
  return <input aria-label={label} className={cx(inputClass, invalid && "border-danger")} aria-invalid={invalid || undefined}
    disabled={disabled} type="number" inputMode="numeric" min={range.min} max={range.max} step="1" value={text}
    onChange={(event) => {
      const next = event.target.value;
      const parsed = parseInteger(next, range);
      setTyped({ text: next, value: parsed === undefined ? value : parsed });
      if (parsed !== undefined) onChange(parsed);
    }} />;
}
