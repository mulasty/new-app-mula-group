import { BillingSnapshot } from "@/shared/api/types";

type PlanUsageBarsProps = {
  billing: BillingSnapshot;
};

function UsageBar({ label, used, limit }: { label: string; used: number; limit: number }): JSX.Element {
  const safeLimit = Math.max(1, limit);
  const percent = Math.min(100, Math.round((used / safeLimit) * 100));
  const color =
    percent >= 100 ? "bg-red-500" : percent >= 80 ? "bg-amber-500" : "bg-emerald-500";

  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-xs text-slate-600">
        <span>{label}</span>
        <span>
          {used}/{limit}
        </span>
      </div>
      <div className="h-2 rounded-full bg-slate-200">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${percent}%` }} />
      </div>
    </div>
  );
}

export function PlanUsageBars({ billing }: PlanUsageBarsProps): JSX.Element {
  const postsUsed = billing.usage.posts_used_current_period ?? 0;
  const projectsUsed = billing.usage.projects_count ?? 0;
  const connectorsUsed = billing.usage.connectors_count ?? 0;

  const over80 =
    (billing.usage.posts_usage_percent ?? 0) >= 80 ||
    (billing.usage.projects_usage_percent ?? 0) >= 80 ||
    (billing.usage.connectors_usage_percent ?? 0) >= 80;

  return (
    <div className="space-y-3">
      {over80 ? (
        <div className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-700">
          Usage above 80%. Upgrade recommended to keep publishing velocity.
        </div>
      ) : null}
      <UsageBar label="Posts / month" used={postsUsed} limit={billing.plan.max_posts_per_month} />
      <UsageBar label="Projects" used={projectsUsed} limit={billing.plan.max_projects} />
      <UsageBar label="Connectors" used={connectorsUsed} limit={billing.plan.max_connectors} />
    </div>
  );
}
