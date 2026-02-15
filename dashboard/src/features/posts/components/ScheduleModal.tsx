import { useEffect, useMemo, useState } from "react";

import { Button } from "@/shared/components/ui/Button";
import { Input } from "@/shared/components/ui/Input";
import { Modal } from "@/shared/components/ui/Modal";

type ScheduleModalProps = {
  open: boolean;
  title: string;
  initialPublishAt?: string | null;
  isSubmitting?: boolean;
  onClose: () => void;
  onSubmit: (publishAtIso: string) => void;
};

function toLocalDateTimeInputValue(value: string | null | undefined): string {
  if (!value) {
    return "";
  }
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) {
    return "";
  }

  const tzOffset = date.getTimezoneOffset();
  const local = new Date(date.getTime() - tzOffset * 60000);
  return local.toISOString().slice(0, 16);
}

export function ScheduleModal({
  open,
  title,
  initialPublishAt,
  isSubmitting,
  onClose,
  onSubmit,
}: ScheduleModalProps): JSX.Element {
  const [publishAtInput, setPublishAtInput] = useState("");

  useEffect(() => {
    if (open) {
      setPublishAtInput(toLocalDateTimeInputValue(initialPublishAt));
    }
  }, [open, initialPublishAt]);

  const validationMessage = useMemo(() => {
    if (!publishAtInput) {
      return "Publish date-time is required.";
    }

    const selected = new Date(publishAtInput);
    if (Number.isNaN(selected.valueOf())) {
      return "Invalid date-time value.";
    }

    if (selected.getTime() < Date.now() - 60000) {
      return "Date-time cannot be in the past.";
    }

    return null;
  }, [publishAtInput]);

  return (
    <Modal
      open={open}
      title={title}
      onClose={onClose}
      footer={
        <>
          <Button type="button" className="bg-slate-200 text-slate-700 hover:bg-slate-300" onClick={onClose}>
            Cancel
          </Button>
          <Button
            type="button"
            disabled={Boolean(validationMessage) || isSubmitting}
            onClick={() => {
              const nextIso = new Date(publishAtInput).toISOString();
              onSubmit(nextIso);
            }}
          >
            {isSubmitting ? "Saving..." : "Save schedule"}
          </Button>
        </>
      }
    >
      <div className="space-y-3">
        <Input
          type="datetime-local"
          value={publishAtInput}
          onChange={(event) => setPublishAtInput(event.target.value)}
        />
        {validationMessage ? <p className="text-xs text-red-600">{validationMessage}</p> : null}
      </div>
    </Modal>
  );
}
