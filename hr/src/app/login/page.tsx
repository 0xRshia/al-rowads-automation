import { redirect } from "next/navigation";
import { CsrfField } from "@/components/CsrfField";
import { StatusMessage } from "@/components/StatusMessage";
import { destinationForRole, getCurrentUser } from "@/lib/auth";

export default async function LoginPage({
  searchParams,
}: Readonly<{ searchParams: Promise<{ error?: string }> }>) {
  const user = await getCurrentUser();
  if (user) {
    redirect(destinationForRole(user.role));
  }

  const params = await searchParams;

  return (
    <main className="flex min-h-screen items-center justify-center px-5 py-10">
      <section className="panel w-full max-w-md p-6 shadow-sm">
        <h1 className="text-2xl font-bold text-slate-950">Sign in</h1>
        <p className="mt-1 text-sm text-slate-600">Use your company HR account.</p>
        <div className="mt-6">
          <StatusMessage error={params.error} />
          <form action="/api/auth/login" className="space-y-4" method="post">
            <CsrfField />
            <label className="block">
              <span className="text-sm font-semibold text-slate-700">Email or username</span>
              <input className="form-input mt-1" name="identifier" required />
            </label>
            <label className="block">
              <span className="text-sm font-semibold text-slate-700">Password</span>
              <input className="form-input mt-1" name="password" required type="password" />
            </label>
            <button className="btn btn-primary w-full" type="submit">
              Log in
            </button>
          </form>
        </div>
      </section>
    </main>
  );
}
