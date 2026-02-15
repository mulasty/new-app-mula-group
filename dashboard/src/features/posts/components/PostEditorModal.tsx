import { zodResolver } from "@hookform/resolvers/zod";
import { useEffect } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Button } from "@/shared/components/ui/Button";
import { Input } from "@/shared/components/ui/Input";
import { Modal } from "@/shared/components/ui/Modal";

const postSchema = z.object({
  title: z.string().trim().min(1, "Title is required").max(255, "Title is too long"),
  content: z.string().trim().min(1, "Content is required"),
});

type PostEditorValues = z.infer<typeof postSchema>;

type PostEditorModalProps = {
  open: boolean;
  title: string;
  initialValues?: Partial<PostEditorValues>;
  isSubmitting?: boolean;
  onClose: () => void;
  onSubmit: (values: PostEditorValues) => void;
};

export function PostEditorModal({
  open,
  title,
  initialValues,
  isSubmitting,
  onClose,
  onSubmit,
}: PostEditorModalProps): JSX.Element {
  const form = useForm<PostEditorValues>({
    resolver: zodResolver(postSchema),
    defaultValues: {
      title: initialValues?.title ?? "",
      content: initialValues?.content ?? "",
    },
  });

  useEffect(() => {
    if (open) {
      form.reset({
        title: initialValues?.title ?? "",
        content: initialValues?.content ?? "",
      });
    }
  }, [open, initialValues, form]);

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
            disabled={isSubmitting}
            onClick={() => {
              void form.handleSubmit((values) => onSubmit(values))();
            }}
          >
            {isSubmitting ? "Saving..." : "Save"}
          </Button>
        </>
      }
    >
      <form className="space-y-3" onSubmit={(event) => event.preventDefault()}>
        <div>
          <Input placeholder="Post title" {...form.register("title")} />
          {form.formState.errors.title ? (
            <p className="mt-1 text-xs text-red-600">{form.formState.errors.title.message}</p>
          ) : null}
        </div>

        <div>
          <textarea
            className="min-h-36 w-full rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-800 outline-none ring-brand-600 focus:ring-2"
            placeholder="Post content"
            {...form.register("content")}
          />
          {form.formState.errors.content ? (
            <p className="mt-1 text-xs text-red-600">{form.formState.errors.content.message}</p>
          ) : null}
        </div>
      </form>
    </Modal>
  );
}
