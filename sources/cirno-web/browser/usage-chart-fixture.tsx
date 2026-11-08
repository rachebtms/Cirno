import { TokenUsageCard } from "@/features/settings/TokenUsageCard";
import { TokenUsageModelTrend } from "@/features/settings/TokenUsageModelTrend";
import type { SettingsPayload } from "@/lib/contracts/settings";

type Usage = NonNullable<SettingsPayload["usage"]>;
const date = new Date().toISOString().slice(0, 10);
const today: Usage["days"][number] = { date, total_tokens: 10000, input_tokens: 9000, output_tokens: 1000,
  cache_read_tokens: 8000, cache_write_tokens: 0, cache_read_observed_input_tokens: 9000,
  cache_write_observed_input_tokens: 0, requests: 5 };
export const fixtureUsage: Usage = {
  days: [{ ...today, sources: { user: { ...today, total_tokens: 9970 }, system: { ...today, total_tokens: 30 } } }],
  total_tokens: 10000, total_tokens_30d: 10000, total_tokens_365d: 10000,
  peak_day_tokens: 10000, current_streak_days: 1, longest_streak_days: 1,
  active_days_30d: 1, requests_30d: 5,
};
const usage = fixtureUsage;
const days = Array.from({ length: 30 }, (_, i) => {
  const value = new Date(`${date}T00:00:00Z`);
  value.setUTCDate(value.getUTCDate() - 29 + i);
  return { date: value.toISOString().slice(0, 10), usage: i === 29 ? today : undefined };
});
export function UsageChartFixture() {
  return <main className="mx-auto max-w-3xl space-y-12 p-4 text-foreground">
    <TokenUsageCard usage={usage} timeZone="UTC" />
    <TokenUsageModelTrend days={days} modelDays={[{ date, provider: "test", model: "DeepSeek", total_tokens: 10000 }]} />
    <button type="button">Outside chart</button>
  </main>;
}
