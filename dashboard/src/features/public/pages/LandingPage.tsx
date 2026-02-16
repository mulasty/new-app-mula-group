import { Link } from "react-router-dom";

import { Button } from "@/shared/components/ui/Button";
import { Card } from "@/shared/components/ui/Card";

export function LandingPage(): JSX.Element {
  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-950 via-slate-900 to-slate-800 px-4 py-10 text-slate-100">
      <div className="mx-auto flex w-full max-w-6xl flex-col gap-10">
        <header className="flex items-center justify-between">
          <div className="text-lg font-bold">Control Center</div>
          <div className="flex items-center gap-2">
            <Link to="/pricing">
              <Button type="button" className="bg-slate-700 hover:bg-slate-600">
                Pricing
              </Button>
            </Link>
            <Link to="/auth">
              <Button type="button">Login</Button>
            </Link>
          </div>
        </header>

        <section className="grid gap-8 lg:grid-cols-[1.3fr_1fr]">
          <div className="space-y-5">
            <h1 className="text-4xl font-black tracking-tight md:text-5xl">
              Multi-tenant marketing automation built for execution.
            </h1>
            <p className="max-w-2xl text-slate-300">
              Create campaigns, automate content, publish across channels, and track outcomes in one control plane.
            </p>
            <div className="flex flex-wrap gap-3">
              <Link to="/pricing">
                <Button type="button">Start free trial</Button>
              </Link>
              <Link to="/auth">
                <Button type="button" className="bg-slate-700 hover:bg-slate-600">
                  Open dashboard
                </Button>
              </Link>
            </div>
          </div>
          <Card className="border-slate-700 bg-slate-900/70">
            <div className="space-y-3">
              <div className="text-sm font-semibold text-brand-300">Release Ready</div>
              <ul className="space-y-2 text-sm text-slate-300">
                <li>Automation runtime with guardrails</li>
                <li>Publishing engine with retries and timeline</li>
                <li>Connector framework for social channels</li>
                <li>Analytics, billing and admin tooling</li>
              </ul>
            </div>
          </Card>
        </section>
      </div>
    </div>
  );
}
