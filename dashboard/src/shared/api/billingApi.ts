import { api } from "@/shared/api/client";
import { BillingPlan, BillingSnapshot } from "@/shared/api/types";

export async function listPublicPlans(): Promise<BillingPlan[]> {
  const response = await api.get<{ items: BillingPlan[]; beta_disabled?: boolean }>("/public/plans");
  if (response.data.beta_disabled) {
    return [];
  }
  return response.data.items ?? [];
}

export async function listBillingPlans(): Promise<BillingPlan[]> {
  const response = await api.get<{ items: BillingPlan[] }>("/billing/plans");
  return response.data.items ?? [];
}

export async function getCurrentBilling(): Promise<BillingSnapshot> {
  const response = await api.get<BillingSnapshot>("/billing/current");
  return response.data;
}

export async function createCheckoutSession(planName: string): Promise<{ checkout_url?: string | null; session_id?: string | null }> {
  const response = await api.post<{ checkout_url?: string | null; session_id?: string | null }>("/billing/checkout-session", {
    plan_name: planName,
  });
  return response.data;
}
