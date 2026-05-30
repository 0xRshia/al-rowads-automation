import { AdminShell } from "@/components/AdminShell";
import { CsrfField } from "@/components/CsrfField";
import { StatusMessage } from "@/components/StatusMessage";
import { requireAdmin } from "@/lib/auth";

export default async function NewEmployeePage({
  searchParams,
}: Readonly<{ searchParams: Promise<{ error?: string }> }>) {
  await requireAdmin();
  const params = await searchParams;

  return (
    <AdminShell title="New Employee">
      <StatusMessage error={params.error} />
      <form action="/api/admin/employees" className="panel grid gap-4 p-5 md:grid-cols-2" method="post">
        <CsrfField />
        <label>
          <span className="text-sm font-semibold">Full name</span>
          <input className="form-input mt-1" name="fullName" required />
        </label>
        <label>
          <span className="text-sm font-semibold">Email</span>
          <input className="form-input mt-1" name="email" required type="email" />
        </label>
        <label>
          <span className="text-sm font-semibold">Username</span>
          <input className="form-input mt-1" name="username" required />
        </label>
        <label>
          <span className="text-sm font-semibold">Role</span>
          <select className="form-input mt-1" name="role" defaultValue="EMPLOYEE">
            <option>EMPLOYEE</option>
            <option>MANAGER</option>
            <option>HR_ADMIN</option>
            <option>SUPER_ADMIN</option>
          </select>
        </label>
        <label className="md:col-span-2">
          <span className="text-sm font-semibold">Initial password</span>
          <input className="form-input mt-1" name="password" required type="password" />
        </label>
        <label className="flex items-center gap-2">
          <input name="isActive" type="hidden" value="false" />
          <input defaultChecked name="isActive" type="checkbox" value="true" />
          <span className="text-sm font-semibold">Active</span>
        </label>
        <div className="md:col-span-2">
          <button className="btn btn-primary" type="submit">
            Create employee
          </button>
        </div>
      </form>
    </AdminShell>
  );
}
