import { QueryCache, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";

import { useToast } from "@/app/providers/ToastProvider";

export function QueryProvider({ children }: { children: React.ReactNode }): JSX.Element {
  const { pushToast } = useToast();
  const [queryClient] = useState(
    () =>
      new QueryClient({
        queryCache: new QueryCache({
          onError: () => pushToast("Data fetch failed", "error"),
        }),
        defaultOptions: {
          queries: {
            retry: 1,
            refetchOnWindowFocus: false,
          },
          mutations: {
            onError: () => pushToast("Operation failed", "error"),
          },
        },
      })
  );

  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}
