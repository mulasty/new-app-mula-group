import { Navigate, createBrowserRouter, RouterProvider } from "react-router-dom";

import { AppShell } from "@/app/layout/AppShell";
import { RootFrame } from "@/app/layout/RootFrame";
import { useAuth } from "@/app/providers/AuthProvider";
import { RouteErrorBoundary } from "@/app/router/RouteErrorBoundary";
import { AuthPage } from "@/features/auth/pages/AuthPage";
import { ChannelsPage } from "@/features/channels/pages/ChannelsPage";
import { DashboardPage } from "@/features/dashboard/pages/DashboardPage";
import { OnboardingPage } from "@/features/onboarding/pages/OnboardingPage";
import { PostsPage } from "@/features/posts/pages/PostsPage";
import { ProjectsPage } from "@/features/projects/pages/ProjectsPage";
import { SettingsPage } from "@/features/settings/pages/SettingsPage";
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
          element: <Navigate to={isAuthenticated ? "/app" : "/auth"} replace />,
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
                { path: "channels", element: <ChannelsPage /> },
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
