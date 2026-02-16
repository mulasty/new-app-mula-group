import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { z } from "zod";

import { useAuth } from "@/app/providers/AuthProvider";
import { useTenant } from "@/app/providers/TenantProvider";
import { useToast } from "@/app/providers/ToastProvider";
import { getApiErrorMessage } from "@/shared/api/errors";
import { Button } from "@/shared/components/ui/Button";
import { Card } from "@/shared/components/ui/Card";
import { Input } from "@/shared/components/ui/Input";

const DEV_DEFAULTS = {
  tenantId: "7f855bba-10be-4410-8083-77949ba33a6b",
  email: "owner@test.local",
  password: "secret123",
};

function shouldUseDevAutofill(): boolean {
  if (!import.meta.env.DEV || typeof window === "undefined") {
    return false;
  }

  return window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1";
}

const loginSchema = z.object({
  email: z.string().email("Podaj poprawny email"),
  password: z.string().min(8, "Haslo min. 8 znakow"),
  tenantId: z.string().uuid("Tenant UUID jest niepoprawny"),
});

const registerSchema = z.object({
  email: z.string().email("Podaj poprawny email"),
  password: z.string().min(8, "Haslo min. 8 znakow"),
  fullName: z.string().min(2, "Podaj imie i nazwisko"),
  companyName: z.string().min(2, "Podaj nazwe firmy"),
});

type LoginValues = z.infer<typeof loginSchema>;
type RegisterValues = z.infer<typeof registerSchema>;

export function AuthPage(): JSX.Element {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { pushToast } = useToast();
  const { loginWithPassword, registerUser } = useAuth();
  const { tenantId, setTenant } = useTenant();
  const [tab, setTab] = useState<"login" | "register">("login");
  const useDevAutofill = shouldUseDevAutofill();

  const [loginValues, setLoginValues] = useState<LoginValues>({
    tenantId: tenantId || (useDevAutofill ? DEV_DEFAULTS.tenantId : ""),
    email: useDevAutofill ? DEV_DEFAULTS.email : "",
    password: useDevAutofill ? DEV_DEFAULTS.password : "",
  });

  const [registerValues, setRegisterValues] = useState<RegisterValues>({
    email: useDevAutofill ? DEV_DEFAULTS.email : "",
    password: useDevAutofill ? DEV_DEFAULTS.password : "",
    fullName: useDevAutofill ? "Demo Owner" : "",
    companyName: useDevAutofill ? "Demo Tenant" : "",
  });

  const [loginErrors, setLoginErrors] = useState<Partial<Record<keyof LoginValues, string>>>({});
  const [registerErrors, setRegisterErrors] = useState<Partial<Record<keyof RegisterValues, string>>>({});
  const [isSubmitting, setIsSubmitting] = useState(false);
  const requestedPlan = searchParams.get("plan");

  useEffect(() => {
    if (!tenantId) {
      return;
    }

    setLoginValues((prev) => ({ ...prev, tenantId: prev.tenantId || tenantId }));
  }, [tenantId]);

  const handleLogin = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setIsSubmitting(true);
    setLoginErrors({});

    const parsed = loginSchema.safeParse(loginValues);
    if (!parsed.success) {
      const fieldErrors = parsed.error.flatten().fieldErrors;
      setLoginErrors({
        tenantId: fieldErrors.tenantId?.[0],
        email: fieldErrors.email?.[0],
        password: fieldErrors.password?.[0],
      });
      setIsSubmitting(false);
      return;
    }

    try {
      setTenant(parsed.data.tenantId);
      await loginWithPassword(parsed.data.email, parsed.data.password);
      navigate(requestedPlan ? `/app/onboarding?plan=${encodeURIComponent(requestedPlan)}` : "/app");
    } catch (error) {
      pushToast(getApiErrorMessage(error, "Login failed"), "error");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleRegister = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setIsSubmitting(true);
    setRegisterErrors({});

    const parsed = registerSchema.safeParse(registerValues);
    if (!parsed.success) {
      const fieldErrors = parsed.error.flatten().fieldErrors;
      setRegisterErrors({
        email: fieldErrors.email?.[0],
        password: fieldErrors.password?.[0],
        fullName: fieldErrors.fullName?.[0],
        companyName: fieldErrors.companyName?.[0],
      });
      setIsSubmitting(false);
      return;
    }

    try {
      const createdTenantId = await registerUser(
        parsed.data.email,
        parsed.data.password,
        parsed.data.fullName,
        parsed.data.companyName
      );
      setTenant(createdTenantId);
      await loginWithPassword(parsed.data.email, parsed.data.password);
      navigate(requestedPlan ? `/app/onboarding?plan=${encodeURIComponent(requestedPlan)}` : "/app");
    } catch (error) {
      pushToast(getApiErrorMessage(error, "Registration failed"), "error");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="grid min-h-screen place-items-center bg-gradient-to-br from-brand-50 via-white to-slate-100 p-4">
      <Card className="w-full max-w-lg">
        <div className="mb-4 grid grid-cols-2 gap-2 rounded-lg bg-slate-100 p-1">
          <button
            type="button"
            className={`rounded-md px-3 py-2 text-sm font-semibold ${tab === "login" ? "bg-white shadow" : "text-slate-600"}`}
            onClick={() => setTab("login")}
          >
            Zaloguj
          </button>
          <button
            type="button"
            className={`rounded-md px-3 py-2 text-sm font-semibold ${tab === "register" ? "bg-white shadow" : "text-slate-600"}`}
            onClick={() => setTab("register")}
          >
            Rejestracja
          </button>
        </div>

        {tab === "login" ? (
          <form className="space-y-3" noValidate onSubmit={handleLogin}>
            <Input
              placeholder="Tenant UUID"
              value={loginValues.tenantId}
              onChange={(event) => setLoginValues((prev) => ({ ...prev, tenantId: event.target.value }))}
            />
            {loginErrors.tenantId ? <p className="text-xs text-red-600">{loginErrors.tenantId}</p> : null}

            <Input
              placeholder="Email"
              value={loginValues.email}
              onChange={(event) => setLoginValues((prev) => ({ ...prev, email: event.target.value }))}
            />
            {loginErrors.email ? <p className="text-xs text-red-600">{loginErrors.email}</p> : null}

            <Input
              type="password"
              placeholder="Haslo"
              value={loginValues.password}
              onChange={(event) => setLoginValues((prev) => ({ ...prev, password: event.target.value }))}
            />
            {loginErrors.password ? <p className="text-xs text-red-600">{loginErrors.password}</p> : null}

            <Button type="submit" className="w-full" disabled={isSubmitting}>
              {isSubmitting ? "Logowanie..." : "Zaloguj"}
            </Button>
          </form>
        ) : (
          <form className="space-y-3" noValidate onSubmit={handleRegister}>
            <Input
              placeholder="Nazwa firmy"
              value={registerValues.companyName}
              onChange={(event) => setRegisterValues((prev) => ({ ...prev, companyName: event.target.value }))}
            />
            {registerErrors.companyName ? <p className="text-xs text-red-600">{registerErrors.companyName}</p> : null}

            <Input
              placeholder="Email"
              value={registerValues.email}
              onChange={(event) => setRegisterValues((prev) => ({ ...prev, email: event.target.value }))}
            />
            {registerErrors.email ? <p className="text-xs text-red-600">{registerErrors.email}</p> : null}

            <Input
              type="password"
              placeholder="Haslo"
              value={registerValues.password}
              onChange={(event) => setRegisterValues((prev) => ({ ...prev, password: event.target.value }))}
            />
            {registerErrors.password ? <p className="text-xs text-red-600">{registerErrors.password}</p> : null}

            <Input
              placeholder="Imie i nazwisko"
              value={registerValues.fullName}
              onChange={(event) => setRegisterValues((prev) => ({ ...prev, fullName: event.target.value }))}
            />
            {registerErrors.fullName ? <p className="text-xs text-red-600">{registerErrors.fullName}</p> : null}

            <Button type="submit" className="w-full" disabled={isSubmitting}>
              {isSubmitting ? "Tworzenie..." : "Utworz konto"}
            </Button>
          </form>
        )}
      </Card>
    </div>
  );
}
