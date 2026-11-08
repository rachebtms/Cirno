export function formatCronScheduleSummary(
  expr: string,
  locale: string,
  tx: (
    key: string,
    fallback: string,
    values?: Record<string, unknown>,
  ) => string,
): string | null {
  const parts = expr.trim().split(/\s+/);
  if (parts.length !== 5) return null;
  const [minute, hour, dayOfMonth, month, dayOfWeek] = parts;
  const numericMinute = cronNumericToken(minute, 59);
  const numericHour = cronNumericToken(hour, 23);
  const everyDay = dayOfMonth === "*" && month === "*" && dayOfWeek === "*";
  const workdays =
    dayOfMonth === "*" &&
    month === "*" &&
    ["1-5", "MON-FRI", "mon-fri"].includes(dayOfWeek);

  if (numericMinute !== null && numericHour !== null) {
    const time = `${String(numericHour).padStart(2, "0")}:${String(numericMinute).padStart(2, "0")}`;
    if (everyDay)
      return tx("settings.automations.schedule.dailyAt", "Daily at {{time}}", {
        time,
      });
    if (workdays)
      return tx(
        "settings.automations.schedule.weekdaysAt",
        "Weekdays at {{time}}",
        { time },
      );
    const weekday = /^\d$/.test(dayOfWeek)
      ? Number(dayOfWeek)
      : ["SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT"].indexOf(
          dayOfWeek.toUpperCase(),
        );
    if (dayOfMonth === "*" && month === "*" && weekday >= 0 && weekday <= 7) {
      return tx(
        "settings.automations.schedule.weeklyAt",
        "Every {{day}} at {{time}}",
        {
          day: new Intl.DateTimeFormat(locale, { weekday: "long" }).format(
            new Date(2024, 0, 7 + (weekday % 7)),
          ),
          time,
        },
      );
    }
    const day = cronNumericToken(dayOfMonth, 31);
    if (day !== null && day > 0 && month === "*" && dayOfWeek === "*") {
      return tx(
        "settings.automations.schedule.monthlyAt",
        "Monthly on day {{day}} at {{time}}",
        { day, time },
      );
    }
  }

  if (everyDay && numericMinute !== null && hour === "*") {
    return tx(
      "settings.automations.schedule.hourlyAt",
      "Hourly at :{{minute}}",
      {
        minute: String(numericMinute).padStart(2, "0"),
      },
    );
  }

  const range = /^(\d{1,2})-(\d{1,2})$/.exec(hour);
  if (everyDay && numericMinute !== null && range) {
    const start = Number(range[1]);
    const end = Number(range[2]);
    if (start > 23 || end > 23) return null;
    return tx(
      "settings.automations.schedule.hourlyWindow",
      "Hourly {{start}}-{{end}} at :{{minute}}",
      {
        start: String(start).padStart(2, "0"),
        end: String(end).padStart(2, "0"),
        minute: String(numericMinute).padStart(2, "0"),
      },
    );
  }

  return null;
}

function cronNumericToken(value: string, max: number): number | null {
  if (!/^\d{1,2}$/.test(value)) return null;
  const parsed = Number(value);
  return parsed <= max ? parsed : null;
}
