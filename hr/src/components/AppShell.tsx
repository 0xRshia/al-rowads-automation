import Link from "next/link";
import { LogoutForm } from "@/components/LogoutForm";

export function AppShell({
  title,
  children,
}: Readonly<{ title: string; children: React.ReactNode }>) {
  return (
    <div className="min-h-screen">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-5xl items-center justify-between gap-4 px-5 py-4">
          <Link className="text-lg font-bold text-slate-950" href="/app/dashboard">
            Company Accounts
          </Link>
          <nav className="flex items-center gap-2 text-sm font-semibold">
            <Link className="btn btn-secondary" href="/app/accounts">
              Accounts
            </Link>
            <LogoutForm />
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-5xl px-5 py-8">
        <h1 className="mb-6 text-3xl font-bold text-slate-950">{title}</h1>
        {children}
      </main>
    </div>
  );
}
