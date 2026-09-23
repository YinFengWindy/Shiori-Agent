import { SITE_SETTINGS_COPY } from "../../content/siteCopy";
import { TEXT_SPEEDS, type TextSpeed } from "../../prefs/sitePrefs";
import { cx } from "../../siteClassNames";

interface TextSpeedPickerProps {
  value: TextSpeed;
  onChange: (value: TextSpeed) => void;
}

/** 慢 / 中 / 快 segmented radio group for the typewriter speed. */
export function TextSpeedPicker({ value, onChange }: TextSpeedPickerProps) {
  return (
    <fieldset className="flex flex-col gap-2">
      <legend className="mb-2 text-body text-site-ink">{SITE_SETTINGS_COPY.textSpeed}</legend>
      <div className="site-segmented grid grid-cols-3 gap-1 rounded-md p-1">
        {TEXT_SPEEDS.map((speed) => (
          <label key={speed} className={cx("site-segmented-option rounded-md text-center text-body-sm", speed === value && "site-segmented-option-active")}>
            <input
              type="radio"
              name="site-text-speed"
              value={speed}
              checked={speed === value}
              onChange={() => onChange(speed)}
              className="sr-only"
            />
            {SITE_SETTINGS_COPY.textSpeedOptions[speed]}
          </label>
        ))}
      </div>
    </fieldset>
  );
}
