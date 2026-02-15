import clsx from "clsx";

import { PostStatus } from "@/shared/api/types";

type StatusChipProps = {
  status: PostStatus;
};

const statusStyles: Record<PostStatus, string> = {
  draft: "border-slate-300 bg-slate-100 text-slate-700",
  scheduled: "border-amber-300 bg-amber-50 text-amber-700",
  publishing: "border-blue-300 bg-blue-50 text-blue-700",
  published: "border-emerald-300 bg-emerald-50 text-emerald-700",
  published_partial: "border-violet-300 bg-violet-50 text-violet-700",
  failed: "border-red-300 bg-red-50 text-red-700",
};

export function StatusChip({ status }: StatusChipProps): JSX.Element {
  return (
    <span
      className={clsx(
        "inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-semibold capitalize",
        statusStyles[status]
      )}
    >
      {status}
    </span>
  );
}
