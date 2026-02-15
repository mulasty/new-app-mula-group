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
            {items.map((event) => (
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
                <pre className="mt-2 overflow-auto rounded-md bg-slate-100 p-2 text-xs text-slate-700">
                  {JSON.stringify(event.metadata_json ?? {}, null, 2)}
                </pre>
              </li>
            ))}
          </ul>
        )}
      </aside>
    </div>,
    document.body
  );
}
