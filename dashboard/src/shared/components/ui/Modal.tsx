import { useEffect } from "react";
import { createPortal } from "react-dom";

import { Button } from "@/shared/components/ui/Button";

type ModalProps = {
  open: boolean;
  title: string;
  onClose: () => void;
  children: React.ReactNode;
  footer?: React.ReactNode;
  maxWidthClassName?: string;
  bodyClassName?: string;
};

export function Modal({
  open,
  title,
  onClose,
  children,
  footer,
  maxWidthClassName = "max-w-lg",
  bodyClassName = "",
}: ModalProps): JSX.Element | null {
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
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-slate-900/50 p-4 md:items-center" onClick={onClose}>
      <div
        className={`my-6 flex max-h-[calc(100vh-3rem)] w-full ${maxWidthClassName} flex-col rounded-xl border border-slate-200 bg-white p-5 shadow-xl`}
        onClick={(event) => event.stopPropagation()}
      >
        <div className="mb-4 flex items-start justify-between gap-4">
          <h3 className="text-lg font-semibold text-slate-900">{title}</h3>
          <Button type="button" className="bg-slate-200 px-2 py-1 text-slate-700 hover:bg-slate-300" onClick={onClose}>
            x
          </Button>
        </div>
        <div className={`min-h-0 overflow-y-auto pr-1 ${bodyClassName}`}>{children}</div>
        {footer ? <div className="mt-5 flex justify-end gap-2">{footer}</div> : null}
      </div>
    </div>,
    document.body
  );
}
