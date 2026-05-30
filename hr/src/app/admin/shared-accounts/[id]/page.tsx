import { notFound } from "next/navigation";
import { AdminShell } from "@/components/AdminShell";
import { CsrfField } from "@/components/CsrfField";
import { StatusMessage } from "@/components/StatusMessage";
import { requireAdmin } from "@/lib/auth";
import { prisma } from "@/lib/prisma";

export default async function SharedAccountDetailPage({
  params,
  searchParams,
}: Readonly<{ params: Promise<{ id: string }>; searchParams: Promise<{ error?: string }> }>) {
  await requireAdmin();
  const [{ id }, query] = await Promise.all([params, searchParams]);
  const [account, users] = await Promise.all([
    prisma.sharedAccount.findFirst({
      where: { id, archivedAt: null },
      include: {
        totpSecret: true,
        accountPermissions: {
          include: { user: true },
          orderBy: { createdAt: "desc" },
        },
      },
    }),
    prisma.user.findMany({
      where: { deletedAt: null, isActive: true },
      orderBy: { fullName: "asc" },
    }),
  ]);

  if (!account) {
    notFound();
  }

  const grantedUserIds = new Set(account.accountPermissions.map((permission) => permission.userId));
  const grantableUsers = users.filter((user) => !grantedUserIds.has(user.id));

  return (
    <AdminShell title={`${account.serviceName}: ${account.accountLabel}`}>
      <StatusMessage error={query.error} />
      <div className="grid gap-5 lg:grid-cols-[2fr_1fr]">
        <form
          action={`/api/admin/shared-accounts/${account.id}`}
          className="panel grid gap-4 p-5 md:grid-cols-2"
          method="post"
        >
          <CsrfField />
          <label>
            <span className="text-sm font-semibold">Service name</span>
            <input className="form-input mt-1" defaultValue={account.serviceName} name="serviceName" required />
          </label>
          <label>
            <span className="text-sm font-semibold">Account label</span>
            <input className="form-input mt-1" defaultValue={account.accountLabel} name="accountLabel" required />
          </label>
          <label className="md:col-span-2">
            <span className="text-sm font-semibold">Login email</span>
            <input className="form-input mt-1" defaultValue={account.loginEmail} name="loginEmail" required type="email" />
          </label>
          <label className="md:col-span-2">
            <span className="text-sm font-semibold">Notes</span>
            <textarea className="form-input mt-1 min-h-28" defaultValue={account.notes || ""} name="notes" />
          </label>
          <label className="flex items-center gap-2">
            <input name="isActive" type="hidden" value="false" />
            <input defaultChecked={account.isActive} name="isActive" type="checkbox" value="true" />
            <span className="text-sm font-semibold">Active</span>
          </label>
          <div className="md:col-span-2">
            <button className="btn btn-primary" type="submit">
              Save changes
            </button>
          </div>
        </form>

        <div className="space-y-4">
          <form action={`/api/admin/shared-accounts/${account.id}`} className="panel space-y-3 p-5" method="post">
            <CsrfField />
            <input name="_action" type="hidden" value="add-totp" />
            <label className="block">
              <span className="text-sm font-semibold">TOTP secret</span>
              <input className="form-input mt-1" name="secret" required />
            </label>
            <p className="text-sm text-slate-600">
              {account.totpSecret ? "A secret is configured." : "No secret configured."}
            </p>
            <button className="btn btn-secondary" type="submit">
              Save encrypted secret
            </button>
          </form>

          <form action={`/api/admin/shared-accounts/${account.id}`} className="panel space-y-3 p-5" method="post">
            <CsrfField />
            <input name="_action" type="hidden" value="disable" />
            <button className="btn btn-secondary" type="submit">
              Disable account
            </button>
          </form>

          <form action={`/api/admin/shared-accounts/${account.id}`} className="panel space-y-3 p-5" method="post">
            <CsrfField />
            <input name="_action" type="hidden" value="archive" />
            <button className="btn btn-danger" type="submit">
              Archive account
            </button>
          </form>
        </div>
      </div>

      <section className="mt-6 grid gap-5 lg:grid-cols-[1fr_1fr]">
        <div className="panel p-5">
          <h2 className="text-xl font-bold">Grant access</h2>
          <form action={`/api/admin/shared-accounts/${account.id}`} className="mt-4 space-y-4" method="post">
            <CsrfField />
            <input name="_action" type="hidden" value="grant" />
            <label className="block">
              <span className="text-sm font-semibold">Employee</span>
              <select className="form-input mt-1" name="userId" required>
                {grantableUsers.map((user) => (
                  <option key={user.id} value={user.id}>
                    {user.fullName} ({user.email})
                  </option>
                ))}
              </select>
            </label>
            <label className="flex items-center gap-2">
              <input name="canViewCode" type="hidden" value="false" />
              <input name="canViewCode" type="checkbox" value="true" />
              <span className="text-sm font-semibold">Can view current 2FA code</span>
            </label>
            <button className="btn btn-secondary" disabled={grantableUsers.length === 0} type="submit">
              Grant access
            </button>
          </form>
        </div>

        <div className="panel overflow-x-auto p-5">
          <h2 className="text-xl font-bold">Permissions</h2>
          <table className="mt-4 w-full text-left text-sm">
            <thead className="text-slate-600">
              <tr>
                <th className="py-2">Employee</th>
                <th className="py-2">Code</th>
                <th className="py-2"></th>
              </tr>
            </thead>
            <tbody>
              {account.accountPermissions.map((permission) => (
                <tr className="border-t border-slate-200" key={permission.id}>
                  <td className="py-3">{permission.user.fullName}</td>
                  <td className="py-3">{permission.canViewCode ? "Allowed" : "Hidden"}</td>
                  <td className="py-3 text-right">
                    <form action={`/api/admin/shared-accounts/${account.id}`} method="post">
                      <CsrfField />
                      <input name="_action" type="hidden" value="revoke" />
                      <input name="userId" type="hidden" value={permission.userId} />
                      <button className="btn btn-secondary" type="submit">
                        Revoke
                      </button>
                    </form>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </AdminShell>
  );
}
