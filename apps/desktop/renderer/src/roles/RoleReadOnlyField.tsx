import type { ReactNode } from "react";
import { cx } from "../shared/styles";
import { roleFieldClass } from "./roleEditorStyles";

/** Role editor field surface shown when its value cannot be edited (locked binding, single choice, no declaration). */
export const roleReadOnlyFieldClass = cx(roleFieldClass, "cursor-default text-ink-muted");

/**
 * Read-only stand-in for a picker: a text box announced as read-only, with
 * the same surface as a locked input so a row keeps its layout.
 */
export function RoleReadOnlyField({ label, children }: { label: string; children: ReactNode }) {
  return <span className={cx(roleReadOnlyFieldClass, "truncate")} role="textbox" aria-label={label} aria-readonly="true">{children}</span>;
}
