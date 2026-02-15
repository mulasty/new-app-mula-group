import { WebsitePublication } from "@/shared/api/types";
import { EmptyState } from "@/shared/components/EmptyState";
import { Card } from "@/shared/components/ui/Card";
import { Spinner } from "@/shared/components/ui/Spinner";

type WebsiteFeedPageProps = {
  publications: WebsitePublication[];
  isLoading: boolean;
  backendMissing?: boolean;
  endpointUnavailable?: boolean;
  onOpenOnboarding?: () => void;
};

export function WebsiteFeedPage({
  publications,
  isLoading,
  backendMissing,
  endpointUnavailable,
  onOpenOnboarding,
}: WebsiteFeedPageProps): JSX.Element {
  return (
    <Card title="Website publications feed">
      {backendMissing ? (
        <div className="mb-3 rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-700">
          Endpoint not available yet. Showing fallback data from mock store.
        </div>
      ) : null}

      {endpointUnavailable ? (
        <div className="mb-3 rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-700">
          Endpoint not available yet. Publish records will appear here once backend route is active.
        </div>
      ) : null}

      {isLoading ? (
        <div className="flex items-center gap-2 text-sm text-slate-600">
          <Spinner /> Loading website feed...
        </div>
      ) : publications.length === 0 ? (
        <EmptyState
          title="No website publications"
          description="Publish your first post to populate this feed."
          actionLabel={onOpenOnboarding ? "Open onboarding" : undefined}
          onAction={onOpenOnboarding}
        />
      ) : (
        <div className="overflow-auto">
          <table className="min-w-full text-left text-sm">
            <thead className="text-slate-500">
              <tr>
                <th className="py-2">Title</th>
                <th className="py-2">Slug</th>
                <th className="py-2">Published at</th>
              </tr>
            </thead>
            <tbody>
              {publications.map((publication) => (
                <tr key={publication.id} className="border-t border-slate-200">
                  <td className="py-2 font-medium text-slate-900">{publication.title}</td>
                  <td className="py-2 font-mono text-xs text-slate-600">{publication.slug}</td>
                  <td className="py-2 text-slate-600">{new Date(publication.published_at).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}
