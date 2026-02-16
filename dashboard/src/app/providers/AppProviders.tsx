import { AuthProvider } from "@/app/providers/AuthProvider";
import { FeatureFlagsProvider } from "@/app/providers/FeatureFlagsProvider";
import { QueryProvider } from "@/app/providers/QueryProvider";
import { TenantProvider } from "@/app/providers/TenantProvider";
import { ToastProvider } from "@/app/providers/ToastProvider";

export function AppProviders({ children }: { children: React.ReactNode }): JSX.Element {
  return (
    <ToastProvider>
      <AuthProvider>
        <TenantProvider>
          <QueryProvider>
            <FeatureFlagsProvider>{children}</FeatureFlagsProvider>
          </QueryProvider>
        </TenantProvider>
      </AuthProvider>
    </ToastProvider>
  );
}
