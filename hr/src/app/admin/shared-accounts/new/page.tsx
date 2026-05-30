import { AdminShell } from "@/components/AdminShell";
import { CsrfField } from "@/components/CsrfField";
import { StatusMessage } from "@/components/StatusMessage";
import { requireAdmin } from "@/lib/auth";

export default async function NewSharedAccountPage({
  searchParams,
}: Readonly<{ searchParams: Promise<{ error?: string }> }>) {
  await requireAdmin();
  const params = await searchParams;

  return (
    <AdminShell title="New Shared Account">
      <StatusMessage error={params.error} />
      <form
        action="/api/admin/shared-accounts"
        className="panel grid gap-4 p-5 md:grid-cols-2"
        method="post"
      >
        <CsrfField />
        <label>
          <span className="text-sm font-semibold">Service name</span>
          <input className="form-input mt-1" name="serviceName" required />
        </label>
        <label>
          <span className="text-sm font-semibold">Account label</span>
          <input className="form-input mt-1" name="accountLabel" required />
        </label>
        <label className="md:col-span-2">
          <span className="text-sm font-semibold">Login email</span>
          <input className="form-input mt-1" name="loginEmail" required type="email" />
        </label>
        <label className="md:col-span-2">
          <span className="text-sm font-semibold">Notes</span>
          <textarea className="form-input mt-1 min-h-28" name="notes" />
        </label>
        <label className="flex items-center gap-2">
          <input name="isActive" type="hidden" value="false" />
          <input defaultChecked name="isActive" type="checkbox" value="true" />
          <span className="text-sm font-semibold">Active</span>
        </label>
        <div className="md:col-span-2">
          <button className="btn btn-primary" type="submit">
            Create account
          </button>
        </div>
      </form>
    </AdminShell>
  );
}
