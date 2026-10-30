/** One read-only label/value row of a details view; an empty value shows a dash. */
export function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="grid gap-1 rounded-md px-3 py-2.5">
      <span className="text-caption font-medium text-ink-muted">{label}</span>
      <span className="break-words text-body-sm text-ink-secondary">{value || "—"}</span>
    </div>
  );
}
