import Link from "next/link";
import { AdminShell } from "@/components/AdminShell";
import { requireAdmin } from "@/lib/auth";
import { prisma } from "@/lib/prisma";

export default async function SharedAccountsPage() {
  await requireAdmin();
  const accounts = await prisma.sharedAccount.findMany({
    where: { archivedAt: null },
    include: { _count: { select: { accountPermissions: true } }, totpSecret: true },
    orderBy: { createdAt: "desc" },
  });

  return (
    <AdminShell title="Shared Accounts">
      <div className="mb-4 flex justify-end">
        <Link className="btn btn-primary" href="/admin/shared-accounts/new">
          New account
        </Link>
      </div>
      <div className="panel overflow-x-auto">
        <table className="w-full min-w-[760px] text-left text-sm">
          <thead className="bg-slate-100 text-slate-600">
            <tr>
              <th className="px-4 py-3">Service</th>
              <th className="px-4 py-3">Label</th>
              <th className="px-4 py-3">Login</th>
              <th className="px-4 py-3">TOTP</th>
              <th className="px-4 py-3">Users</th>
              <th className="px-4 py-3">Status</th>
            </tr>
          </thead>
          <tbody>
            {accounts.map((account) => (
              <tr className="border-t border-slate-200" key={account.id}>
                <td className="px-4 py-3 font-semibold">
                  <Link className="text-blue-800" href={`/admin/shared-accounts/${account.id}`}>
                    {account.serviceName}
                  </Link>
                </td>
                <td className="px-4 py-3">{account.accountLabel}</td>
                <td className="px-4 py-3">{account.loginEmail}</td>
                <td className="px-4 py-3">{account.totpSecret ? "Configured" : "Missing"}</td>
                <td className="px-4 py-3">{account._count.accountPermissions}</td>
                <td className="px-4 py-3">{account.isActive ? "Active" : "Disabled"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </AdminShell>
  );
}
