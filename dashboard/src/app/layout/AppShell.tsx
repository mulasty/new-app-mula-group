import { useEffect, useMemo, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";

import { useAuth } from "@/app/providers/AuthProvider";
import { useTenant } from "@/app/providers/TenantProvider";
import { Button } from "@/shared/components/ui/Button";
import { Input } from "@/shared/components/ui/Input";
import { Modal } from "@/shared/components/ui/Modal";

const navItems = [
  { to: "/app", label: "Dashboard" },
  { to: "/app/posts", label: "Posts" },
  { to: "/app/projects", label: "Projects" },
  { to: "/app/campaigns", label: "Campaigns" },
  { to: "/app/automations", label: "Automations" },
  { to: "/app/content-studio", label: "Content Studio" },
  { to: "/app/calendar", label: "Calendar" },
  { to: "/app/channels", label: "Channels" },
  { to: "/app/settings", label: "Settings" },
  { to: "/app/onboarding", label: "Onboarding" },
];

const uuidPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

export function AppShell(): JSX.Element {
  const location = useLocation();
  const navigate = useNavigate();
  const { user, logout } = useAuth();
  const { tenantId, setTenant, discoverTenant, isTenantLoading } = useTenant();

  const [isTenantModalOpen, setTenantModalOpen] = useState(false);
  const [isLogoutModalOpen, setLogoutModalOpen] = useState(false);
  const [isPaletteOpen, setPaletteOpen] = useState(false);
  const [tenantDraft, setTenantDraft] = useState(tenantId);

  useEffect(() => {
    setTenantDraft(tenantId);
  }, [tenantId]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setPaletteOpen((value) => !value);
      }
    };

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  const tenantShort = useMemo(() => (tenantId ? `${tenantId.slice(0, 8)}...` : "Not set"), [tenantId]);

  return (
    <div className="min-h-screen bg-slate-100">
      <div className="grid min-h-screen grid-cols-1 lg:grid-cols-[240px_1fr]">
        <aside className="border-r border-slate-200 bg-slate-900 p-4 text-slate-200">
          <div className="mb-8 text-lg font-bold">Control Center</div>
          <nav className="space-y-1">
            {navItems.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === "/app"}
                className={({ isActive }) =>
                  `block rounded-md px-3 py-2 text-sm ${isActive ? "bg-slate-800 text-white" : "text-slate-300 hover:bg-slate-800"}`
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>

          <Button
            type="button"
            className="mt-6 w-full bg-slate-700 hover:bg-slate-600"
            onClick={() => setPaletteOpen(true)}
          >
            Command Palette (Ctrl+K)
          </Button>
        </aside>

        <main>
          <header className="flex flex-col gap-3 border-b border-slate-200 bg-white p-4 md:flex-row md:items-center md:justify-between">
            <div className="flex items-center gap-2">
              <div className="rounded-md bg-slate-100 px-3 py-2 text-sm text-slate-700">Tenant: {tenantShort}</div>
              <Button type="button" className="bg-slate-700 hover:bg-slate-600" onClick={() => setTenantModalOpen(true)}>
                Change tenant
              </Button>
            </div>

            <div className="flex items-center gap-3">
              <div className="text-sm text-slate-600">{user?.email ?? "unknown user"}</div>
              <Button type="button" onClick={() => setLogoutModalOpen(true)} className="bg-slate-900 hover:bg-slate-800">
                Logout
              </Button>
            </div>
          </header>

          <section className="p-4 md:p-6">
            <Outlet />
          </section>
        </main>
      </div>

      <Modal
        open={isTenantModalOpen}
        title="Change tenant"
        onClose={() => setTenantModalOpen(false)}
        footer={
          <>
            <Button type="button" className="bg-slate-200 text-slate-700 hover:bg-slate-300" onClick={() => setTenantModalOpen(false)}>
              Cancel
            </Button>
            <Button
              type="button"
              onClick={() => {
                if (!uuidPattern.test(tenantDraft)) {
                  return;
                }
                setTenant(tenantDraft);
                setTenantModalOpen(false);
              }}
            >
              Save
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          <Input value={tenantDraft} onChange={(event) => setTenantDraft(event.target.value)} placeholder="Tenant UUID" />
          {!uuidPattern.test(tenantDraft || "") ? (
            <div className="text-xs text-red-600">Provide valid UUID.</div>
          ) : null}
          <Button
            type="button"
            className="w-full bg-slate-700 hover:bg-slate-600"
            onClick={() => void discoverTenant()}
            disabled={isTenantLoading}
          >
            {isTenantLoading ? "Detecting..." : "Use auto-detected tenant"}
          </Button>
        </div>
      </Modal>

      <Modal
        open={isLogoutModalOpen}
        title="Confirm logout"
        onClose={() => setLogoutModalOpen(false)}
        footer={
          <>
            <Button type="button" className="bg-slate-200 text-slate-700 hover:bg-slate-300" onClick={() => setLogoutModalOpen(false)}>
              Cancel
            </Button>
            <Button
              type="button"
              className="bg-red-600 hover:bg-red-500"
              onClick={() => {
                setLogoutModalOpen(false);
                logout();
              }}
            >
              Logout
            </Button>
          </>
        }
      >
        <p className="text-sm text-slate-600">You will be signed out from Control Center dashboard.</p>
      </Modal>

      <Modal open={isPaletteOpen} title="Quick navigation" onClose={() => setPaletteOpen(false)}>
        <div className="space-y-2">
          {navItems.map((item) => (
            <button
              key={item.to}
              type="button"
              onClick={() => {
                navigate(item.to);
                setPaletteOpen(false);
              }}
              className={`w-full rounded-md border px-3 py-2 text-left text-sm ${
                location.pathname === item.to ? "border-brand-700 bg-brand-50" : "border-slate-200"
              }`}
            >
              {item.label}
            </button>
          ))}
        </div>
      </Modal>
    </div>
  );
}
