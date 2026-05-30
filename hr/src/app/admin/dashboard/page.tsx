import Link from "next/link";
import { AdminShell } from "@/components/AdminShell";
import { requireAdmin } from "@/lib/auth";
import { prisma } from "@/lib/prisma";

export default async function AdminDashboardPage() {
  await requireAdmin();
  const [users, sharedAccounts, auditLogs] = await Promise.all([
    prisma.user.count({ where: { deletedAt: null } }),
    prisma.sharedAccount.count({ where: { archivedAt: null } }),
    prisma.auditLog.count(),
  ]);

  return (
    <AdminShell title="Dashboard">
      <div className="grid gap-4 md:grid-cols-3">
        {[
          { label: "Employees", value: users, href: "/admin/employees" },
          { label: "Shared accounts", value: sharedAccounts, href: "/admin/shared-accounts" },
          { label: "Audit events", value: auditLogs, href: "/admin/audit-logs" },
        ].map((item) => (
          <Link className="panel block p-5 shadow-sm" href={item.href} key={item.label}>
            <p className="text-sm font-semibold text-slate-500">{item.label}</p>
            <p className="mt-2 text-4xl font-bold text-slate-950">{item.value}</p>
          </Link>
        ))}
      </div>
    </AdminShell>
  );
}
