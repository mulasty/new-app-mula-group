import { createContext, useContext, useEffect, useMemo, useState } from "react";

import { useToast } from "@/app/providers/ToastProvider";
import { getTenantContext } from "@/shared/api/tenantApi";
import { TenantContextResponse } from "@/shared/api/types";
import { getTenantId, setTenantId } from "@/shared/utils/storage";

type TenantContextType = {
  tenantId: string;
  tenantContext: TenantContextResponse | null;
  isContextKnown: boolean;
  isTenantLoading: boolean;
  setTenant: (tenantId: string) => void;
  discoverTenant: () => Promise<void>;
};

const TenantContext = createContext<TenantContextType | null>(null);

export function TenantProvider({ children }: { children: React.ReactNode }): JSX.Element {
  const { pushToast } = useToast();
  const [tenantId, setTenantIdState] = useState<string>(getTenantId() ?? "");
  const [tenantContext, setTenantContext] = useState<TenantContextResponse | null>(null);
  const [isContextKnown, setIsContextKnown] = useState<boolean>(Boolean(getTenantId()));
  const [isTenantLoading, setIsTenantLoading] = useState(false);

  const setTenant = (nextTenantId: string): void => {
    setTenantId(nextTenantId);
    setTenantIdState(nextTenantId);
    setIsContextKnown(true);
  };

  const discoverTenant = async (): Promise<void> => {
    setIsTenantLoading(true);
    try {
      const context = await getTenantContext();
      setTenantContext(context);
      const resolved = context.current_tenant_id ?? context.tenant_id ?? context.tenants?.[0]?.id;
      if (resolved) {
        setTenant(resolved);
      }
      setIsContextKnown(true);
    } catch {
      pushToast("Tenant context unavailable. Set tenant manually.", "info");
      setIsContextKnown(false);
    } finally {
      setIsTenantLoading(false);
    }
  };

  useEffect(() => {
    if (!tenantId) {
      void discoverTenant();
    }
  }, []);

  const value = useMemo(
    () => ({ tenantId, tenantContext, isContextKnown, isTenantLoading, setTenant, discoverTenant }),
    [tenantId, tenantContext, isContextKnown, isTenantLoading]
  );

  return <TenantContext.Provider value={value}>{children}</TenantContext.Provider>;
}

export function useTenant(): TenantContextType {
  const context = useContext(TenantContext);
  if (!context) {
    throw new Error("useTenant must be used inside TenantProvider");
  }
  return context;
}
