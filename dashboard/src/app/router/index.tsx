import { Navigate, createBrowserRouter, RouterProvider } from "react-router-dom";

import { AppShell } from "@/app/layout/AppShell";
import { AdminPage } from "@/features/admin/pages/AdminPage";
import { RootFrame } from "@/app/layout/RootFrame";
import { useAuth } from "@/app/providers/AuthProvider";
import { RouteErrorBoundary } from "@/app/router/RouteErrorBoundary";
import { AuthPage } from "@/features/auth/pages/AuthPage";
import { ChannelsPage } from "@/features/channels/pages/ChannelsPage";
import { CampaignsPage } from "@/features/campaigns/pages/CampaignsPage";
import { DashboardPage } from "@/features/dashboard/pages/DashboardPage";
import { OnboardingPage } from "@/features/onboarding/pages/OnboardingPage";
import { LandingPage } from "@/features/public/pages/LandingPage";
import { PricingPage } from "@/features/public/pages/PricingPage";
import { PostsPage } from "@/features/posts/pages/PostsPage";
import { ProjectsPage } from "@/features/projects/pages/ProjectsPage";
import { SettingsPage } from "@/features/settings/pages/SettingsPage";
import { AutomationsPage } from "@/features/automations/pages/AutomationsPage";
import { ContentStudioPage } from "@/features/content-studio/pages/ContentStudioPage";
import { CalendarPage } from "@/features/calendar/pages/CalendarPage";
import { ProtectedRoute } from "@/shared/components/ProtectedRoute";

export function AppRouter(): JSX.Element {
  const { isAuthenticated } = useAuth();

  const router = createBrowserRouter([
    {
      element: <RootFrame />,
      errorElement: <RouteErrorBoundary />,
      children: [
        {
          path: "/",
          element: <LandingPage />,
        },
        {
          path: "/pricing",
          element: <PricingPage />,
        },
        {
          path: "/auth",
          element: isAuthenticated ? <Navigate to="/app" replace /> : <AuthPage />,
        },
        {
          element: <ProtectedRoute />,
          children: [
            {
              path: "/app",
              element: <AppShell />,
              children: [
                { index: true, element: <DashboardPage /> },
                { path: "onboarding", element: <OnboardingPage /> },
                { path: "posts", element: <PostsPage /> },
                { path: "projects", element: <ProjectsPage /> },
                { path: "campaigns", element: <CampaignsPage /> },
                { path: "automations", element: <AutomationsPage /> },
                { path: "content-studio", element: <ContentStudioPage /> },
                { path: "calendar", element: <CalendarPage /> },
                { path: "channels", element: <ChannelsPage /> },
                { path: "admin", element: <AdminPage /> },
                { path: "settings", element: <SettingsPage /> },
              ],
            },
          ],
        },
      ],
    },
  ]);

  return <RouterProvider router={router} />;
}
