import { useNavigation } from "react-router-dom";

export function RouteLoadingBar(): JSX.Element {
  const navigation = useNavigation();
  const isLoading = navigation.state === "loading";

  return (
    <div className="pointer-events-none fixed left-0 top-0 z-[60] h-1 w-full bg-transparent">
      <div
        className={`h-full bg-brand-700 transition-all duration-300 ${isLoading ? "w-1/2 opacity-100" : "w-0 opacity-0"}`}
      />
    </div>
  );
}
