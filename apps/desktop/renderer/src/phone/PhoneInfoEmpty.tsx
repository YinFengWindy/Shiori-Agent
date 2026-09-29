/** Quiet placeholder line of an empty chat info block or profile. */
export function PhoneInfoEmpty({ label }: { label: string }) {
  return <p className="m-0 px-0.5 text-body-sm text-ink-muted">{label}</p>;
}
