import { forwardRef, type CSSProperties, type TextareaHTMLAttributes } from "react";
import { cx } from "../styles";

type AutosizeTextareaProps = Omit<TextareaHTMLAttributes<HTMLTextAreaElement>, "value"> & {
  value: string;
  containerClassName?: string;
  /** Inline style for the sizing container, e.g. a `maxHeight` past which the textarea scrolls. */
  containerStyle?: CSSProperties;
  mirrorClassName?: string;
};

/** Renders a textarea whose height follows its content without synchronous DOM measurement. */
export const AutosizeTextarea = forwardRef<HTMLTextAreaElement, AutosizeTextareaProps>(
  function AutosizeTextarea({ value, className, containerClassName, containerStyle, mirrorClassName, ...textareaProps }, ref) {
    return (
      <div className={cx("grid min-w-0 grid-cols-[minmax(0,1fr)]", containerClassName)} style={{ contain: "layout", ...containerStyle }}>
        <div
          aria-hidden="true"
          className={cx(
            // A long unbroken word must not enlarge the grid's intrinsic width;
            // the mirror can also shrink when the caller caps the editor height.
            "pointer-events-none invisible col-start-1 row-start-1 min-h-0 min-w-0 overflow-hidden whitespace-pre-wrap [overflow-wrap:anywhere]",
            mirrorClassName,
          )}
          data-autosize-textarea-mirror=""
        >
          {`${value} `}
        </div>
        <textarea
          {...textareaProps}
          ref={ref}
          className={cx("col-start-1 row-start-1 h-full min-w-0 resize-none overflow-hidden [overflow-wrap:anywhere]", className)}
          value={value}
        />
      </div>
    );
  },
);
