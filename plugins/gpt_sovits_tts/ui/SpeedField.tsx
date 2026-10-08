import { useState } from "react";
import { cx, inputClass } from "@yinfengwindy/shiori-sdk";

/** The speed the synthesis service accepts, or null for text outside 0.5–2. */
export function parseSpeed(text: string) {
  const speed = text.trim() === "" ? Number.NaN : Number(text);
  return speed >= 0.5 && speed <= 2 ? speed : null;
}

/**
 * Typed text is shown only while it still belongs to the stored speed it was
 * typed against; a reload, retry or normalised save shows the stored value.
 */
export function SpeedField({ value, disabled, onChange }: { value: number; disabled: boolean; onChange(speed: number): void }) {
  const [typed, setTyped] = useState<{ text: string; speed: number } | null>(null);
  const text = typed && typed.speed === value ? typed.text : String(value);
  const invalid = parseSpeed(text) === null;
  return <label className="grid gap-2">语速<input aria-label="语速" className={cx(inputClass, invalid && "border-danger")} aria-invalid={invalid || undefined}
    disabled={disabled} type="number" min="0.5" max="2" step="0.1" value={text}
    onChange={(event) => {
      const next = event.target.value;
      const speed = parseSpeed(next);
      // Valid text moves the draft and stays shown against it; invalid text stays against the current speed.
      setTyped({ text: next, speed: speed ?? value });
      if (speed !== null) onChange(speed);
    }} /></label>;
}
