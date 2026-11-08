import type { ThemePair } from "./contracts";
export function ThemePreview({ theme }: { theme: ThemePair }) {
  return (
    <span
      className="grid grid-cols-2 overflow-hidden rounded-xl border border-border"
      aria-hidden
    >
      {(["light", "dark"] as const).map((mode) => {
        const palette = theme[mode];
        return (
          <span
            key={mode}
            className="flex h-20 gap-2 p-2.5"
            style={{ background: palette.background, color: palette.text }}
          >
            <span
              className="w-3 shrink-0 rounded-md"
              style={{ background: palette.surface }}
            />
            <span className="flex flex-1 flex-col gap-1.5 py-1">
              <span
                className="h-1 w-3/5 rounded"
                style={{ background: palette.text, opacity: 0.7 }}
              />
              <span
                className="ml-auto h-3 w-2/3 rounded-md"
                style={{
                  background: palette.panel,
                  border: `1px solid ${palette.border}`,
                }}
              />
              <span
                className="h-1 w-4/5 rounded"
                style={{ background: palette.muted, opacity: 0.5 }}
              />
              <span
                className="mt-auto h-1 w-1/3 rounded"
                style={{ background: palette.accent }}
              />
            </span>
          </span>
        );
      })}
    </span>
  );
}
