import type { EventLog } from "../shared/types";

type DiagnosticsPanelProps = {
  error: string;
  events: EventLog[];
  expanded: boolean;
};

/** Renders bridge diagnostics when enabled or when an error is present. */
export function DiagnosticsPanel({ error, events, expanded }: DiagnosticsPanelProps) {
  if (expanded) {
    return (
      <section className="event-panel">
        <div className="panel-head">
          <h3>Bridge Events</h3>
          {error ? <span className="error-chip">{error}</span> : null}
        </div>
        <div className="event-list">
          {events.length ? events.map((event, index) => (
            <article key={`${event.method}-${index}`} className="event-row">
              <div className="event-method">{event.method}</div>
              <pre>{JSON.stringify(event.payload, null, 2)}</pre>
            </article>
          )) : (
            <div className="empty-card">No events yet.</div>
          )}
        </div>
      </section>
    );
  }

  if (!error) {
    return null;
  }

  return (
    <section className="event-panel collapsed-diagnostics">
      <div className="panel-head">
        <h3>Diagnostics</h3>
        <span className="error-chip">{error}</span>
      </div>
    </section>
  );
}
