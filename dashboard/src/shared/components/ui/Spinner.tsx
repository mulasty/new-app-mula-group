import clsx from "clsx";

export function Spinner({ className }: { className?: string }): JSX.Element {
  return (
    <span
      className={clsx(
        "inline-block h-4 w-4 animate-spin rounded-full border-2 border-slate-300 border-t-slate-700",
        className
      )}
    />
  );
}
