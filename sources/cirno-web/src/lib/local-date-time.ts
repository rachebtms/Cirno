export function parseLocalDay(value: string): Date | null {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return null;
  const [year, month, day] = value.split("-").map(Number);
  const date = new Date(0);
  date.setHours(12, 0, 0, 0);
  date.setFullYear(year, month - 1, day);
  return year > 0 && date.getFullYear() === year && date.getMonth() === month - 1 && date.getDate() === day
    ? date
    : null;
}
export function parseLocalDateTime(value: string): Date | null {
  const [day, time, extra] = value.split("T");
  const date = parseLocalDay(day);
  if (!date || extra !== undefined || !/^([01]\d|2[0-3]):[0-5]\d$/.test(time ?? "")) return null;
  const [hour, minute] = time.split(":").map(Number);
  date.setHours(hour, minute, 0, 0);
  return date.getHours() === hour && date.getMinutes() === minute ? date : null;
}
export function localDateTimeInput(ms: number): string {
  const date = new Date(ms);
  return new Date(ms - date.getTimezoneOffset() * 60_000).toISOString().slice(0, 16);
}
