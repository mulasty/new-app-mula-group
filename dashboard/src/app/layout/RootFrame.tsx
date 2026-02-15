import { Outlet } from "react-router-dom";

import { RouteLoadingBar } from "@/shared/components/RouteLoadingBar";

export function RootFrame(): JSX.Element {
  return (
    <>
      <RouteLoadingBar />
      <Outlet />
    </>
  );
}
