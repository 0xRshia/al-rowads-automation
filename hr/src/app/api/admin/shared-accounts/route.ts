import { NextResponse, type NextRequest } from "next/server";
import { AuditAction, logAuditEvent } from "@/lib/audit";
import { requireAdmin } from "@/lib/auth";
import { verifyCsrf } from "@/lib/csrf";
import { prisma } from "@/lib/prisma";
import { getClientIp, getUserAgent } from "@/lib/request";
import { sharedAccountSchema } from "@/lib/validation";

export async function POST(request: NextRequest) {
  const actor = await requireAdmin();
  const formData = await request.formData();

  if (!verifyCsrf(request, formData)) {
    return NextResponse.json({ error: "Invalid request." }, { status: 403 });
  }

  const parsed = sharedAccountSchema.safeParse(Object.fromEntries(formData));
  if (!parsed.success) {
    return NextResponse.redirect(new URL("/admin/shared-accounts/new?error=invalid", request.url));
  }

  const account = await prisma.sharedAccount.create({
    data: {
      serviceName: parsed.data.serviceName,
      accountLabel: parsed.data.accountLabel,
      loginEmail: parsed.data.loginEmail,
      notes: parsed.data.notes || null,
      isActive: parsed.data.isActive,
    },
  });

  await logAuditEvent({
    actorId: actor.id,
    sharedAccountId: account.id,
    action: AuditAction.SHARED_ACCOUNT_CREATED,
    ipAddress: getClientIp(request),
    userAgent: getUserAgent(request),
  });

  return NextResponse.redirect(new URL(`/admin/shared-accounts/${account.id}`, request.url));
}
