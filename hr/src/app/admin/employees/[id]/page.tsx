import { notFound } from "next/navigation";
import { AdminShell } from "@/components/AdminShell";
import { CsrfField } from "@/components/CsrfField";
import { StatusMessage } from "@/components/StatusMessage";
import { requireAdmin } from "@/lib/auth";
import { prisma } from "@/lib/prisma";

export default async function EmployeeDetailPage({
  params,
  searchParams,
}: Readonly<{ params: Promise<{ id: string }>; searchParams: Promise<{ error?: string }> }>) {
  await requireAdmin();
  const [{ id }, query] = await Promise.all([params, searchParams]);
  const user = await prisma.user.findFirst({ where: { id, deletedAt: null } });

  if (!user) {
    notFound();
  }

  return (
    <AdminShell title={user.fullName}>
      <StatusMessage error={query.error} />
      <div className="grid gap-5 lg:grid-cols-[2fr_1fr]">
        <form
          action={`/api/admin/employees/${user.id}`}
          className="panel grid gap-4 p-5 md:grid-cols-2"
          method="post"
        >
          <CsrfField />
          <label>
            <span className="text-sm font-semibold">Full name</span>
            <input className="form-input mt-1" defaultValue={user.fullName} name="fullName" required />
          </label>
          <label>
            <span className="text-sm font-semibold">Email</span>
            <input className="form-input mt-1" defaultValue={user.email} name="email" required type="email" />
          </label>
          <label>
            <span className="text-sm font-semibold">Username</span>
            <input className="form-input mt-1" defaultValue={user.username} name="username" required />
          </label>
          <label>
            <span className="text-sm font-semibold">Role</span>
            <select className="form-input mt-1" defaultValue={user.role} name="role">
              <option>EMPLOYEE</option>
              <option>MANAGER</option>
              <option>HR_ADMIN</option>
              <option>SUPER_ADMIN</option>
            </select>
          </label>
          <label className="flex items-center gap-2">
            <input name="isActive" type="hidden" value="false" />
            <input defaultChecked={user.isActive} name="isActive" type="checkbox" value="true" />
            <span className="text-sm font-semibold">Active</span>
          </label>
          <div className="md:col-span-2">
            <button className="btn btn-primary" type="submit">
              Save changes
            </button>
          </div>
        </form>

        <div className="space-y-4">
          <form action={`/api/admin/employees/${user.id}`} className="panel space-y-3 p-5" method="post">
            <CsrfField />
            <input name="_action" type="hidden" value="reset-password" />
            <label className="block">
              <span className="text-sm font-semibold">New password</span>
              <input className="form-input mt-1" name="password" required type="password" />
            </label>
            <button className="btn btn-secondary" type="submit">
              Reset password
            </button>
          </form>
          <form action={`/api/admin/employees/${user.id}`} className="panel space-y-3 p-5" method="post">
            <CsrfField />
            <input name="_action" type="hidden" value="disable" />
            <button className="btn btn-secondary" type="submit">
              Disable account
            </button>
          </form>
          <form action={`/api/admin/employees/${user.id}`} className="panel space-y-3 p-5" method="post">
            <CsrfField />
            <input name="_action" type="hidden" value="delete" />
            <button className="btn btn-danger" type="submit">
              Soft-delete account
            </button>
          </form>
        </div>
      </div>
    </AdminShell>
  );
}
