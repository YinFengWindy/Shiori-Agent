import type { ReactNode } from "react";
import { roleSectionTitleClass } from "./roleEditorStyles";

type RoleEditorSectionProps = {
  title: string;
  /** Optional control shown at the right end of the title row (an add button, a switch). */
  action?: ReactNode;
  children: ReactNode;
  "data-testid"?: string;
};

/**
 * One titled group of fields in the role editor. Consecutive sections are
 * separated by a hairline and the same spacing, so every tab reads as the
 * same stack of groups rather than a wall of boxes.
 */
export function RoleEditorSection({ title, action, children, ...rest }: RoleEditorSectionProps) {
  return (
    <section className="grid gap-4 border-t border-line-soft pt-7 first:border-t-0 first:pt-0" data-testid={rest["data-testid"]}>
      <div className="flex min-h-9 items-center justify-between gap-4">
        <h2 className={roleSectionTitleClass}>{title}</h2>
        {action}
      </div>
      {children}
    </section>
  );
}
