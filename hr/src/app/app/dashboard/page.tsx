import Link from "next/link";
import { AppShell } from "@/components/AppShell";
import { requireUser } from "@/lib/auth";
import { prisma } from "@/lib/prisma";

export default async function EmployeeDashboardPage() {
  const user = await requireUser();
  const count = await prisma.accountPermission.count({
    where: {
      userId: user.id,
      sharedAccount: { isActive: true, archivedAt: null },
    },
  });

  return (
    <AppShell title={`Welcome, ${user.fullName}`}>
      <Link className="panel block p-5 shadow-sm" href="/app/accounts">
        <p className="text-sm font-semibold text-slate-500">Assigned accounts</p>
        <p className="mt-2 text-4xl font-bold text-slate-950">{count}</p>
      </Link>
    </AppShell>
  );
}
