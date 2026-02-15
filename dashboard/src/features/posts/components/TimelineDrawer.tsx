import { useEffect } from "react";
import { createPortal } from "react-dom";

import { PublishEvent } from "@/shared/api/types";
import { Spinner } from "@/shared/components/ui/Spinner";

type TimelineDrawerProps = {
  open: boolean;
  postTitle?: string;
  items: PublishEvent[];
  isLoading: boolean;
  backendMissing?: boolean;
  errorMessage?: string | null;
  onClose: () => void;
};

export function TimelineDrawer({
  open,
  postTitle,
  items,
  isLoading,
  backendMissing,
  errorMessage,
  onClose,
}: TimelineDrawerProps): JSX.Element | null {
  useEffect(() => {
    if (!open) {
      return;
    }

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
      }
    };

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, onClose]);

  if (!open) {
    return null;
  }

  return createPortal(
    <div className="fixed inset-0 z-50 bg-slate-900/40" onClick={onClose}>
      <aside
        className="absolute right-0 top-0 h-full w-full max-w-xl overflow-y-auto border-l border-slate-200 bg-white p-5 shadow-xl"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="mb-4 flex items-start justify-between gap-3">
          <div>
            <h3 className="text-lg font-semibold text-slate-900">Publish timeline</h3>
            {postTitle ? <p className="text-sm text-slate-500">{postTitle}</p> : null}
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md border border-slate-300 px-2 py-1 text-sm text-slate-700 hover:bg-slate-100"
          >
            Close
          </button>
        </div>

        {backendMissing ? (
          <div className="mb-4 rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-700">
            Endpoint not available yet. Showing fallback timeline data.
          </div>
        ) : null}

        {errorMessage ? (
          <div className="mb-4 rounded-md border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-700">
            {errorMessage}
          </div>
        ) : null}

        {isLoading ? (
          <div className="flex items-center gap-2 text-sm text-slate-600">
            <Spinner /> Loading timeline...
          </div>
        ) : items.length === 0 ? (
          <div className="rounded-md border border-dashed border-slate-300 bg-slate-50 p-4 text-sm text-slate-600">
            No publish events for this post yet.
          </div>
        ) : (
          <ul className="space-y-3">
            {items.map((event) => {
              const metadata = event.metadata_json ?? {};
              const publishDurationMs = (() => {
                if (typeof metadata.publish_latency_ms === "number") {
                  return metadata.publish_latency_ms;
                }
                if (typeof metadata.publish_duration_ms === "number") {
                  return metadata.publish_duration_ms;
                }
                return null;
              })();
              const adapterType = typeof metadata.adapter_type === "string" ? metadata.adapter_type : null;
              const channelType = typeof metadata.channel_type === "string" ? metadata.channel_type : null;
              const retryable = typeof metadata.retryable === "boolean" ? metadata.retryable : null;
              const retryCount = typeof metadata.retry_count === "number" ? metadata.retry_count : null;
              return (
                <li key={event.id} className="rounded-lg border border-slate-200 p-3">
                  <div className="flex items-center justify-between gap-3">
                    <div className="font-semibold text-slate-900">{event.event_type}</div>
                    <span
                      className={`rounded-full px-2 py-0.5 text-xs font-semibold ${
                        event.status === "ok" ? "bg-emerald-50 text-emerald-700" : "bg-red-50 text-red-700"
                      }`}
                    >
                      {event.status}
                    </span>
                  </div>
                  <div className="mt-1 text-xs text-slate-500">
                    attempt #{event.attempt} | {new Date(event.created_at).toLocaleString()}
                  </div>
                  <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
                    {channelType ? (
                      <span className="rounded bg-slate-100 px-2 py-0.5 text-slate-700">channel: {channelType}</span>
                    ) : null}
                    {adapterType ? (
                      <span className="rounded bg-blue-50 px-2 py-0.5 text-blue-700">adapter: {adapterType}</span>
                    ) : null}
                    {publishDurationMs !== null ? (
                      <span className="rounded bg-indigo-50 px-2 py-0.5 text-indigo-700">
                        latency: {publishDurationMs} ms
                      </span>
                    ) : null}
                    {retryable !== null ? (
                      <span className="rounded bg-amber-50 px-2 py-0.5 text-amber-700">
                        retryable: {retryable ? "yes" : "no"}
                      </span>
                    ) : null}
                    {retryCount !== null ? (
                      <span className="rounded bg-slate-100 px-2 py-0.5 text-slate-700">
                        retries: {retryCount}
                      </span>
                    ) : null}
                  </div>
                  <pre className="mt-2 overflow-auto rounded-md bg-slate-100 p-2 text-xs text-slate-700">
                    {JSON.stringify(metadata, null, 2)}
                  </pre>
                </li>
              );
            })}
          </ul>
        )}
      </aside>
    </div>,
    document.body
  );
}
