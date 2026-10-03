import { AutosizeTextarea, cx } from "@yinfengwindy/shiori-sdk";
import type { CSSProperties } from "react";
import { roleFieldClass, roleFieldLabelClass } from "./roleEditorStyles";

type RoleTextareaFieldProps = {
  /** Visible label; when omitted, `ariaLabel` names the field (e.g. under a section title that already says it). */
  label?: string;
  ariaLabel?: string;
  value: string;
  placeholder?: string;
  /** Height the field starts at; it grows with its content from there. */
  minHeightClass?: "min-h-24" | "min-h-32" | "min-h-40";
  /** Caps the editor height; longer content scrolls within this field. */
  maxHeight?: CSSProperties["maxHeight"];
  disabled?: boolean;
  "data-testid"?: string;
  onChange: (value: string) => void;
};

// The mirror must share the textarea's box model and type so both wrap identically.
const mirrorBoxClass = "border border-transparent px-3.5 py-2.5 text-body leading-6";

/** Shared role-editor text field, growing with its content up to an optional height limit. */
export function RoleTextareaField({
  label,
  ariaLabel,
  value,
  placeholder,
  minHeightClass = "min-h-24",
  maxHeight,
  disabled,
  onChange,
  ...rest
}: RoleTextareaFieldProps) {
  const field = (
    <AutosizeTextarea
      aria-label={label ? undefined : ariaLabel}
      className={cx(roleFieldClass, "leading-6", minHeightClass, maxHeight !== undefined && "overflow-y-auto")}
      style={{ maxHeight }}
      containerClassName={minHeightClass}
      containerStyle={{ maxHeight }}
      mirrorClassName={cx(mirrorBoxClass, minHeightClass)}
      data-testid={rest["data-testid"]}
      rows={1}
      value={value}
      placeholder={placeholder}
      disabled={disabled}
      onChange={(event) => onChange(event.target.value)}
    />
  );
  if (!label) return field;
  return (
    <label className={roleFieldLabelClass}>
      <span>{label}</span>
      {field}
    </label>
  );
}
