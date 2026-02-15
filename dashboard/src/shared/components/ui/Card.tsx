import clsx from "clsx";

export function Card({
  title,
  children,
  className,
}: {
  title?: string;
  children: React.ReactNode;
  className?: string;
}): JSX.Element {
  return (
    <section className={clsx("rounded-xl border border-slate-200 bg-white p-5 shadow-sm", className)}>
      {title ? <h3 className="mb-4 text-sm font-semibold text-slate-700">{title}</h3> : null}
      {children}
    </section>
  );
}
