import { useMemo } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";

import { useAuth } from "@/app/providers/AuthProvider";
import { useToast } from "@/app/providers/ToastProvider";
import { createCheckoutSessionByPlanId, listPublicPlans } from "@/shared/api/billingApi";
import { getApiErrorMessage } from "@/shared/api/errors";
import { Button } from "@/shared/components/ui/Button";
import { Card } from "@/shared/components/ui/Card";

export function PricingPage(): JSX.Element {
  const navigate = useNavigate();
  const { isAuthenticated } = useAuth();
  const { pushToast } = useToast();
  const plansQuery = useQuery({
    queryKey: ["publicPlans"],
    queryFn: listPublicPlans,
  });

  const checkoutMutation = useMutation({
    mutationFn: (planId: string) => createCheckoutSessionByPlanId(planId),
    onSuccess: (result) => {
      if (result.checkout_url) {
        window.location.assign(result.checkout_url);
        return;
      }
      pushToast("Checkout currently unavailable for selected plan.", "error");
    },
    onError: (error) => {
      pushToast(getApiErrorMessage(error, "Failed to start checkout"), "error");
    },
  });

  const plans = useMemo(() => plansQuery.data ?? [], [plansQuery.data]);
  const pricingEnabled = plans.length > 0;

  return (
    <div className="min-h-screen bg-slate-100 px-4 py-10">
      <div className="mx-auto w-full max-w-6xl space-y-8">
        <header className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold text-slate-900">Pricing</h1>
            <p className="text-sm text-slate-600">Choose the plan matching your growth stage.</p>
          </div>
          <Link to="/">
            <Button type="button" className="bg-slate-700 hover:bg-slate-600">
              Back
            </Button>
          </Link>
        </header>

        {!pricingEnabled ? (
          <Card>
            <p className="text-sm text-slate-600">Pricing beta is currently disabled for this tenant/environment.</p>
          </Card>
        ) : plansQuery.isLoading ? (
          <Card>
            <p className="text-sm text-slate-600">Loading plans...</p>
          </Card>
        ) : (
          <div className="grid gap-4 md:grid-cols-3">
            {plans.map((plan) => (
              <Card key={plan.id} className="flex flex-col gap-4">
                <div>
                  <h2 className="text-xl font-bold text-slate-900">{plan.name}</h2>
                  <p className="text-3xl font-black text-slate-900">${plan.monthly_price}/mo</p>
                </div>
                <ul className="space-y-1 text-sm text-slate-600">
                  <li>{plan.max_projects} projects</li>
                  <li>{plan.max_posts_per_month} posts/month</li>
                  <li>{plan.max_connectors} connectors</li>
                </ul>
                <Button
                  type="button"
                  disabled={checkoutMutation.isPending}
                  onClick={() => {
                    if (!isAuthenticated) {
                      navigate(`/auth?plan=${encodeURIComponent(plan.name)}`);
                      return;
                    }
                    checkoutMutation.mutate(plan.id);
                  }}
                >
                  {isAuthenticated ? "Checkout" : "Get started"}
                </Button>
              </Card>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
