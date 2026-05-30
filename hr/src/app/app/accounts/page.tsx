import Link from "next/link";
import { AppShell } from "@/components/AppShell";
import { requireUser } from "@/lib/auth";
import { prisma } from "@/lib/prisma";

export default async function EmployeeAccountsPage() {
  const user = await requireUser();
  const permissions = await prisma.accountPermission.findMany({
    where: {
      userId: user.id,
      sharedAccount: { isActive: true, archivedAt: null },
    },
    include: { sharedAccount: true },
    orderBy: { sharedAccount: { serviceName: "asc" } },
  });

  return (
    <AppShell title="Assigned Accounts">
      <div className="grid gap-4 md:grid-cols-2">
        {permissions.map((permission) => (
          <Link
            className="panel block p-5 shadow-sm"
            href={`/app/accounts/${permission.sharedAccountId}`}
            key={permission.id}
          >
            <p className="text-xl font-bold text-slate-950">{permission.sharedAccount.serviceName}</p>
            <p className="mt-1 text-slate-700">{permission.sharedAccount.accountLabel}</p>
            <p className="mt-3 text-sm font-semibold text-slate-500">
              Code access: {permission.canViewCode ? "Allowed" : "Hidden"}
            </p>
          </Link>
        ))}
      </div>
    </AppShell>
  );
}
