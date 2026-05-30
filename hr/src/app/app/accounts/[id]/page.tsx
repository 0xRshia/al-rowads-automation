import { notFound, redirect } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { TotpCodePanel } from "@/components/TotpCodePanel";
import { requireUser } from "@/lib/auth";
import { canViewSharedAccount } from "@/lib/authorization";
import { prisma } from "@/lib/prisma";

export default async function EmployeeAccountDetailPage({
  params,
}: Readonly<{ params: Promise<{ id: string }> }>) {
  const user = await requireUser();
  const { id } = await params;
  const permission = await prisma.accountPermission.findUnique({
    where: {
      userId_sharedAccountId: {
        userId: user.id,
        sharedAccountId: id,
      },
    },
    include: {
      sharedAccount: {
        include: { totpSecret: true },
      },
    },
  });

  if (!permission) {
    notFound();
  }

  if (!canViewSharedAccount(user, permission.sharedAccount, permission)) {
    redirect("/app/accounts");
  }

  return (
    <AppShell title={permission.sharedAccount.serviceName}>
      <section className="panel space-y-5 p-5">
        <div>
          <p className="text-sm font-semibold text-slate-500">Account</p>
          <p className="text-xl font-bold text-slate-950">{permission.sharedAccount.accountLabel}</p>
          <p className="mt-1 text-slate-700">{permission.sharedAccount.loginEmail}</p>
        </div>
        {permission.sharedAccount.notes ? (
          <div>
            <p className="text-sm font-semibold text-slate-500">Notes</p>
            <p className="whitespace-pre-wrap text-slate-700">{permission.sharedAccount.notes}</p>
          </div>
        ) : null}
        {permission.canViewCode ? (
          <TotpCodePanel accountId={permission.sharedAccountId} />
        ) : (
          <p className="font-semibold text-slate-700">You can access this account, but 2FA codes are hidden.</p>
        )}
      </section>
    </AppShell>
  );
}
