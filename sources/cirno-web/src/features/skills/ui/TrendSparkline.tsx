import { useTranslation } from "react-i18next";
export function TrendSparkline({ values }: { values?: number[] }) {
  const { t } = useTranslation();
  const trendLabel = t("settings.skills.marketplaceTrendLabel", {
    defaultValue: "8-week install trend",
  });

  if (values === undefined) {
    return <span className="hidden h-[30px] w-24 shrink-0 @min-[640px]/cirno-tab:block" aria-hidden />;
  }
  if (values.length < 2) {
    return (
      <span className="hidden w-24 shrink-0 text-center text-[11px] text-muted-foreground/60 @min-[640px]/cirno-tab:block">
        {t("settings.skills.marketplaceNoTrend", { defaultValue: "No trend yet" })}
      </span>
    );
  }

  const width = 96;
  const height = 30;
  const padding = 2;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = Math.max(max - min, 1);
  const points = values.map((value, index) => ({
    x: padding + (index / (values.length - 1)) * (width - padding * 2),
    y: padding + ((max - value) / range) * (height - padding * 2),
  }));
  const line = points.slice(1).reduce((path, point, index) => {
    const previous = points[index];
    const middle = (previous.x + point.x) / 2;
    return `${path} C ${middle} ${previous.y}, ${middle} ${point.y}, ${point.x} ${point.y}`;
  }, `M ${points[0].x} ${points[0].y}`);
  const area = `${line} L ${points.at(-1)?.x ?? width} ${height} L ${points[0].x} ${height} Z`;

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      className="hidden h-[30px] w-24 shrink-0 overflow-visible text-foreground/40 @min-[640px]/cirno-tab:block"
      role="img"
      aria-label={trendLabel}
    >
      <title>{trendLabel}</title>
      <path d={area} fill="currentColor" opacity="0.06" />
      <path
        d={line}
        fill="none"
        stroke="currentColor"
        strokeWidth="1.4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
