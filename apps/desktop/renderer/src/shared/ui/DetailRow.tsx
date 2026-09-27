/** One read-only label/value row of a details view; an empty value shows a dash. */
export function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="grid gap-1 rounded-md px-3 py-2.5">
      <span className="text-[10px] font-medium tracking-wide text-ink-faint">{label}</span>
      <span className="break-words text-xs leading-5 text-ink-secondary">{value || "—"}</span>
    </div>
  );
}
