import { ActivityStreamItem } from "@/shared/api/types";
import { Card } from "@/shared/components/ui/Card";

type ActivityStreamProps = {
  items: ActivityStreamItem[];
  isLoading: boolean;
  errorMessage?: string | null;
};

export function ActivityStream({ items, isLoading, errorMessage }: ActivityStreamProps): JSX.Element {
  if (errorMessage) {
    return (
      <Card className="border-red-200 bg-red-50">
        <div className="text-sm font-semibold text-red-700">Activity stream unavailable</div>
        <div className="mt-1 text-sm text-red-600">{errorMessage}</div>
      </Card>
    );
  }

  return (
    <Card title="Activity stream">
      {isLoading ? (
        <div className="space-y-2">
          {Array.from({ length: 6 }).map((_, index) => (
            <div key={index} className="h-14 animate-pulse rounded bg-slate-100" />
          ))}
        </div>
      ) : items.length === 0 ? (
        <div className="rounded-md border border-dashed border-slate-300 bg-slate-50 p-4 text-sm text-slate-600">
          No publish activity yet.
        </div>
      ) : (
        <ul className="space-y-2">
          {items.map((item, index) => (
            <li key={`${item.post_id}-${item.timestamp}-${index}`} className="rounded-md border border-slate-200 px-3 py-2">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="font-medium text-slate-900">{item.event_type}</div>
                <span
                  className={`rounded-full px-2 py-0.5 text-xs font-semibold ${
                    item.status === "ok" ? "bg-emerald-50 text-emerald-700" : "bg-red-50 text-red-700"
                  }`}
                >
                  {item.status}
                </span>
              </div>
              <div className="mt-1 text-xs text-slate-500">
                Post {item.post_id.slice(0, 8)} | {new Date(item.timestamp).toLocaleString()}
              </div>
              <pre className="mt-2 overflow-auto rounded bg-slate-100 p-2 text-xs text-slate-700">
                {JSON.stringify(item.metadata ?? {}, null, 2)}
              </pre>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
