import { isRouteErrorResponse, useRouteError } from "react-router-dom";

export function RouteErrorBoundary(): JSX.Element {
  const error = useRouteError();

  if (isRouteErrorResponse(error)) {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-red-700">
        {error.status} - {error.statusText}
      </div>
    );
  }

  return <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-red-700">Unexpected error</div>;
}
