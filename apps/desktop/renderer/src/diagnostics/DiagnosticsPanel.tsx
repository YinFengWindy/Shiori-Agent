import type { EventLog } from "../shared/types";
import { bodyTextClass, cardClass, cx, panelHeadClass, panelTitleClass } from "../shared/styles";

type DiagnosticsPanelProps = {
  error: string;
  events: EventLog[];
  expanded: boolean;
};

/** Renders bridge diagnostics when enabled or when an error is present. */
export function DiagnosticsPanel({ error, events, expanded }: DiagnosticsPanelProps) {
  if (expanded) {
    return (
      <section className="event-panel grid min-h-0 grid-rows-[auto_1fr]">
        <div className={panelHeadClass}>
          <h3 className={panelTitleClass}>Bridge Events</h3>
          {error ? <span className="error-chip rounded-full border border-[rgba(138,50,17,0.18)] bg-[rgba(138,50,17,0.1)] px-3 py-2 text-accent-deep">{error}</span> : null}
        </div>
        <div className={cx("event-list mt-5 grid content-start gap-3", bodyTextClass)}>
          {events.length ? events.map((event, index) => (
            <article key={`${event.method}-${index}`} className={cx("event-row", cardClass, "p-4")}>
              <div className="event-method mb-2 font-bold text-accent-deep">{event.method}</div>
              <pre>{JSON.stringify(event.payload, null, 2)}</pre>
            </article>
          )) : (
            <div className={cx("empty-card", cardClass, "p-4")}>No events yet.</div>
          )}
        </div>
      </section>
    );
  }

  if (!error) {
    return null;
  }

  return (
    <section className="event-panel collapsed-diagnostics grid grid-rows-[auto]">
      <div className={panelHeadClass}>
        <h3 className={panelTitleClass}>Diagnostics</h3>
        <span className="error-chip rounded-full border border-[rgba(138,50,17,0.18)] bg-[rgba(138,50,17,0.1)] px-3 py-2 text-accent-deep">{error}</span>
      </div>
    </section>
  );
}
