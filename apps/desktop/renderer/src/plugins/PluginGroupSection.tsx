import { useId, useState, type ReactNode } from "react";
import { SettingsDisclosure, SettingsDisclosureToggle } from "../settings/SettingsDisclosure";
import { cardClass, cx } from "../shared/styles";
import type { PluginGroup } from "./pluginPresentation";

const groupTitleClass = "text-body-sm font-semibold text-ink-secondary";

/**
 * One titled card of the plugin list. A collapsible group (系统组件) starts
 * closed; its header still reports how many of its plugins have a problem,
 * so a failure inside is not hidden by the fold.
 */
export function PluginGroupSection({ group, problemCount, children }: {
  group: PluginGroup;
  problemCount: number;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(!group.collapsible);
  const bodyId = useId();
  const count = <span className="text-caption tabular-nums text-ink-muted">{group.plugins.length}</span>;
  const problems = problemCount > 0 ? <span className="text-caption text-danger-text">{problemCount} 项异常</span> : null;
  const body = <div className={cx(cardClass, "grid px-4 sm:px-5")}>{children}</div>;
  return (
    <section className="grid gap-2.5" aria-label={group.title} data-plugin-group={group.category}>
      {group.collapsible ? (
        <>
          <SettingsDisclosureToggle open={open} controls={bodyId} onToggle={() => setOpen((current) => !current)}>
            <span>{group.title}</span>
            {count}
            {problems}
          </SettingsDisclosureToggle>
          <SettingsDisclosure open={open} id={bodyId}>{body}</SettingsDisclosure>
        </>
      ) : (
        <>
          <div className="flex items-center gap-2 px-1">
            <h3 className={cx("m-0", groupTitleClass)}>{group.title}</h3>
            {count}
            {problems}
          </div>
          {body}
        </>
      )}
    </section>
  );
}
