import { PublishingTimeRange, PublishingTimeseriesPoint } from "@/shared/api/types";
import { Button } from "@/shared/components/ui/Button";
import { Card } from "@/shared/components/ui/Card";

type PublishingChartProps = {
  points: PublishingTimeseriesPoint[];
  range: PublishingTimeRange;
  onRangeChange: (nextRange: PublishingTimeRange) => void;
  isLoading: boolean;
  errorMessage?: string | null;
};

const RANGE_OPTIONS: PublishingTimeRange[] = ["7d", "30d", "90d"];

export function PublishingChart({
  points,
  range,
  onRangeChange,
  isLoading,
  errorMessage,
}: PublishingChartProps): JSX.Element {
  if (errorMessage) {
    return (
      <Card className="border-red-200 bg-red-50">
        <div className="text-sm font-semibold text-red-700">Publishing chart unavailable</div>
        <div className="mt-1 text-sm text-red-600">{errorMessage}</div>
      </Card>
    );
  }

  const maxValue = Math.max(1, ...points.map((point) => point.published + point.failed));

  return (
    <Card title="Publishing performance">
      <div className="mb-4 flex flex-wrap items-center gap-2">
        {RANGE_OPTIONS.map((option) => (
          <Button
            key={option}
            type="button"
            className={option === range ? "" : "bg-slate-600 hover:bg-slate-500"}
            onClick={() => onRangeChange(option)}
          >
            {option}
          </Button>
        ))}
      </div>

      {isLoading ? (
        <div className="space-y-2">
          {Array.from({ length: 8 }).map((_, index) => (
            <div key={index} className="h-8 animate-pulse rounded bg-slate-100" />
          ))}
        </div>
      ) : points.length === 0 ? (
        <div className="rounded-md border border-dashed border-slate-300 bg-slate-50 p-4 text-sm text-slate-600">
          No publishing data for selected range.
        </div>
      ) : (
        <div className="space-y-2">
          {points.map((point) => {
            const total = point.published + point.failed;
            const totalWidth = `${Math.max(2, (total / maxValue) * 100)}%`;
            const publishedWidth = total > 0 ? `${(point.published / total) * 100}%` : "0%";

            return (
              <div key={point.date} className="grid grid-cols-[90px_1fr_auto] items-center gap-3 text-sm">
                <div className="font-mono text-xs text-slate-500">{point.date.slice(5)}</div>
                <div className="h-6 rounded bg-slate-100">
                  <div className="flex h-full rounded" style={{ width: totalWidth }}>
                    <div
                      className="h-full rounded-l bg-emerald-500"
                      style={{ width: publishedWidth }}
                      title={`Published: ${point.published}`}
                    />
                    <div
                      className="h-full rounded-r bg-red-500"
                      style={{ width: `calc(100% - ${publishedWidth})` }}
                      title={`Failed: ${point.failed}`}
                    />
                  </div>
                </div>
                <div className="text-xs text-slate-600">
                  <span className="font-semibold text-emerald-700">{point.published}</span> /{" "}
                  <span className="font-semibold text-red-700">{point.failed}</span>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </Card>
  );
}
