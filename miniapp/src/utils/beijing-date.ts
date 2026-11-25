const dayMs = 86_400_000;
const beijingOffsetMs = 8 * 3_600_000;

export function beijingClock(value: string | number = Date.now()) {
  return new Date(new Date(value).getTime() + beijingOffsetMs);
}

export function beijingDate(value: string | number = Date.now()) {
  return beijingClock(value).toISOString().slice(0, 10);
}

function civilTime(date: string) {
  return Date.parse(date + "T00:00:00Z");
}

export function shiftDate(date: string, days: number) {
  return new Date(civilTime(date) + days * dayMs).toISOString().slice(0, 10);
}

export function daysBetween(start: string, end: string) {
  return (civilTime(end) - civilTime(start)) / dayMs;
}

export function weekOf(date: string) {
  const day = new Date(civilTime(date)).getUTCDay();
  const monday = shiftDate(date, -((day + 6) % 7));
  return Array.from({ length: 7 }, (_, index) => shiftDate(monday, index));
}
