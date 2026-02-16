import { useMemo, useState } from "react";

const TOOLTIP_STORAGE_PREFIX = "cc_tooltip_seen";

type SmartTooltipProps = {
  id: string;
  title: string;
  message: string;
};

function hasSeenTooltip(id: string): boolean {
  try {
    return localStorage.getItem(`${TOOLTIP_STORAGE_PREFIX}:${id}`) === "1";
  } catch {
    return false;
  }
}

function markSeen(id: string): void {
  try {
    localStorage.setItem(`${TOOLTIP_STORAGE_PREFIX}:${id}`, "1");
  } catch {
    // noop
  }
}

export function SmartTooltip({ id, title, message }: SmartTooltipProps): JSX.Element | null {
  const [dismissed, setDismissed] = useState(false);
  const visible = useMemo(() => !dismissed && !hasSeenTooltip(id), [dismissed, id]);
  if (!visible) {
    return null;
  }

  return (
    <div className="rounded-md border border-brand-200 bg-brand-50 px-3 py-2 text-xs text-brand-900">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="font-semibold">{title}</div>
          <div className="text-brand-800">{message}</div>
        </div>
        <button
          type="button"
          className="rounded px-2 py-1 text-brand-700 hover:bg-brand-100"
          onClick={() => {
            markSeen(id);
            setDismissed(true);
          }}
        >
          Got it
        </button>
      </div>
    </div>
  );
}
