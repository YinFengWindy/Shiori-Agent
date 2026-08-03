const storyDateTimeFormatter = new Intl.DateTimeFormat("sv-SE", {
  calendar: "iso8601",
  day: "2-digit",
  hour: "2-digit",
  hourCycle: "h23",
  minute: "2-digit",
  month: "2-digit",
  timeZone: "Asia/Shanghai",
  year: "numeric",
});

/** Formats a Story timestamp for compact Beijing-time display. */
export function formatStoryDateTime(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "" : storyDateTimeFormatter.format(date);
}
