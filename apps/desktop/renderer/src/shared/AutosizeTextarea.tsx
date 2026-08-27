import { forwardRef, type TextareaHTMLAttributes } from "react";
import { cx } from "./styles";

type AutosizeTextareaProps = Omit<TextareaHTMLAttributes<HTMLTextAreaElement>, "value"> & {
  value: string;
  containerClassName?: string;
  mirrorClassName?: string;
};

/** Renders a textarea whose height follows its content without synchronous DOM measurement. */
export const AutosizeTextarea = forwardRef<HTMLTextAreaElement, AutosizeTextareaProps>(
  function AutosizeTextarea({ value, className, containerClassName, mirrorClassName, ...textareaProps }, ref) {
    return (
      <div className={cx("grid min-w-0", containerClassName)} style={{ contain: "layout" }}>
        <div
          aria-hidden="true"
          className={cx(
            "pointer-events-none invisible col-start-1 row-start-1 whitespace-pre-wrap break-words",
            mirrorClassName,
          )}
          data-autosize-textarea-mirror=""
        >
          {`${value} `}
        </div>
        <textarea
          {...textareaProps}
          ref={ref}
          className={cx("col-start-1 row-start-1 h-full resize-none overflow-hidden", className)}
          value={value}
        />
      </div>
    );
  },
);
