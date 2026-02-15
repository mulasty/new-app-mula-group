type ErrorBadgeProps = {
  message?: string | null;
};

export function ErrorBadge({ message }: ErrorBadgeProps): JSX.Element | null {
  if (!message) {
    return null;
  }

  return (
    <span
      title={message}
      className="inline-flex cursor-help items-center rounded-md border border-red-300 bg-red-50 px-2 py-0.5 text-xs font-medium text-red-700"
    >
      Error details
    </span>
  );
}
