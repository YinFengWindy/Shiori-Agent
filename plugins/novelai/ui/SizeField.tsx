import { cx, inputClass } from "../../../apps/desktop/renderer/src/shared/styles";
import { Select } from "../../../apps/desktop/renderer/src/shared/ui/Select";
import { clampCustomDimensionInput, sizeOptions } from "./studioForm";
import type { ImageSizePreset, ImageStudioFormState } from "./types";

/** Caption above one studio form field. */
export const studioFieldLabelClass = "text-caption font-medium text-ink-secondary";

type SizeFieldProps = {
  form: Pick<ImageStudioFormState, "sizePreset" | "customWidth" | "customHeight">;
  validationError: string;
  onChange: (next: Partial<ImageStudioFormState>) => void;
};

/** Output size: a named preset, or a custom width × height within NovelAI's pixel budget. */
export function SizeField({ form, validationError, onChange }: SizeFieldProps) {
  return (
    <div className="grid gap-1.5">
      <span className={studioFieldLabelClass}>尺寸</span>
      <Select
        aria-label="尺寸"
        className={cx(inputClass, "h-10 py-0")}
        value={form.sizePreset}
        options={sizeOptions}
        onValueChange={(value) => onChange({ sizePreset: value as ImageSizePreset })}
      />
      {form.sizePreset === "custom" ? (
        <div className="grid grid-cols-2 gap-2">
          <input
            className={cx(inputClass, "h-10 py-0")}
            inputMode="numeric"
            aria-label="宽度"
            placeholder="宽度"
            value={form.customWidth}
            onChange={(event) => onChange({ customWidth: clampCustomDimensionInput(event.target.value) })}
          />
          <input
            className={cx(inputClass, "h-10 py-0")}
            inputMode="numeric"
            aria-label="高度"
            placeholder="高度"
            value={form.customHeight}
            onChange={(event) => onChange({ customHeight: clampCustomDimensionInput(event.target.value) })}
          />
        </div>
      ) : null}
      {validationError ? <p className="m-0 text-caption text-danger-text" role="alert">{validationError}</p> : null}
    </div>
  );
}
