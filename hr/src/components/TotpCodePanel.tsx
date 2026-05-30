"use client";

import { useEffect, useState } from "react";

type CodeState =
  | { status: "idle" | "loading"; code?: string; secondsRemaining?: number; error?: string }
  | { status: "ready"; code: string; secondsRemaining: number; error?: string }
  | { status: "error"; error: string; code?: string; secondsRemaining?: number };

export function TotpCodePanel({ accountId }: Readonly<{ accountId: string }>) {
  const [state, setState] = useState<CodeState>({ status: "idle" });

  useEffect(() => {
    let active = true;
    let timeout: ReturnType<typeof setTimeout>;

    async function loadCode() {
      setState((current) => ({ ...current, status: "loading" }));
      const response = await fetch(`/api/app/accounts/${accountId}/code`, {
        cache: "no-store",
      });
      const payload = await response.json();

      if (!active) {
        return;
      }

      if (!response.ok) {
        setState({ status: "error", error: payload.error || "Code unavailable." });
        timeout = setTimeout(loadCode, 10000);
        return;
      }

      setState({
        status: "ready",
        code: payload.code,
        secondsRemaining: payload.secondsRemaining,
      });
    }

    loadCode();
    return () => {
      active = false;
      clearTimeout(timeout);
    };
  }, [accountId]);

  useEffect(() => {
    if (state.status !== "ready") {
      return;
    }

    if (state.secondsRemaining <= 1) {
      const timeout = setTimeout(() => setState({ status: "idle" }), 1000);
      return () => clearTimeout(timeout);
    }

    const interval = setInterval(() => {
      setState((current) =>
        current.status === "ready"
          ? { ...current, secondsRemaining: current.secondsRemaining - 1 }
          : current,
      );
    }, 1000);

    return () => clearInterval(interval);
  }, [state]);

  useEffect(() => {
    if (state.status === "idle") {
      void fetch(`/api/app/accounts/${accountId}/code`, { cache: "no-store" })
        .then((response) => response.json().then((payload) => ({ response, payload })))
        .then(({ response, payload }) => {
          if (!response.ok) {
            setState({ status: "error", error: payload.error || "Code unavailable." });
            return;
          }
          setState({
            status: "ready",
            code: payload.code,
            secondsRemaining: payload.secondsRemaining,
          });
        });
    }
  }, [accountId, state.status]);

  if (state.status === "error") {
    return <p className="font-semibold text-red-700">{state.error}</p>;
  }

  return (
    <div className="flex flex-wrap items-end gap-4">
      <div>
        <p className="text-sm font-semibold text-slate-500">Current code</p>
        <p className="font-mono text-5xl font-bold tracking-[0.18em] text-slate-950">
          {state.status === "ready" ? state.code : "------"}
        </p>
      </div>
      <p className="pb-2 text-sm font-semibold text-slate-600">
        {state.status === "ready" ? `${state.secondsRemaining}s remaining` : "Loading"}
      </p>
    </div>
  );
}
