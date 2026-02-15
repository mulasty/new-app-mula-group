import clsx from "clsx";
import { forwardRef, InputHTMLAttributes } from "react";

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(
  ({ className, ...props }, ref) => (
    <input
      ref={ref}
      className={clsx(
        "w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-800 outline-none ring-brand-600 placeholder:text-slate-400 focus:ring-2",
        className
      )}
      {...props}
    />
  )
);

Input.displayName = "Input";
