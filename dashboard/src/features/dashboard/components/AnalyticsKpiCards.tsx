import { PublishingSummary } from "@/shared/api/types";
import { Card } from "@/shared/components/ui/Card";

type AnalyticsKpiCardsProps = {
  data?: PublishingSummary;
  isLoading: boolean;
  errorMessage?: string | null;
};

function MetricCard({
  label,
  value,
  loading,
}: {
  label: string;
  value: string | number;
  loading: boolean;
}): JSX.Element {
  return (
    <Card>
      <div className="text-sm text-slate-500">{label}</div>
      {loading ? (
        <div className="mt-2 h-8 w-20 animate-pulse rounded bg-slate-200" />
      ) : (
        <div className="mt-1 text-3xl font-bold text-slate-900">{value}</div>
      )}
    </Card>
  );
}

export function AnalyticsKpiCards({ data, isLoading, errorMessage }: AnalyticsKpiCardsProps): JSX.Element {
  if (errorMessage) {
    return (
      <Card className="border-red-200 bg-red-50">
        <div className="text-sm font-semibold text-red-700">Analytics unavailable</div>
        <div className="mt-1 text-sm text-red-600">{errorMessage}</div>
      </Card>
    );
  }

  const summary = data ?? {
    scheduled: 0,
    publishing: 0,
    published: 0,
    failed: 0,
    success_rate: 0,
    avg_publish_time_sec: 0,
  };

  return (
    <div className="grid gap-4 md:grid-cols-3 xl:grid-cols-6">
      <MetricCard label="Scheduled" value={summary.scheduled} loading={isLoading} />
      <MetricCard label="Publishing" value={summary.publishing} loading={isLoading} />
      <MetricCard label="Published" value={summary.published} loading={isLoading} />
      <MetricCard label="Failed" value={summary.failed} loading={isLoading} />
      <MetricCard
        label="Success rate"
        value={`${(summary.success_rate * 100).toFixed(1)}%`}
        loading={isLoading}
      />
      <MetricCard
        label="Avg publish time"
        value={`${summary.avg_publish_time_sec.toFixed(1)}s`}
        loading={isLoading}
      />
    </div>
  );
}
