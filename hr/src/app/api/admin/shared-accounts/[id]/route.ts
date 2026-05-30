import { NextResponse, type NextRequest } from "next/server";
import { AuditAction, logAuditEvent } from "@/lib/audit";
import { requireAdmin } from "@/lib/auth";
import { verifyCsrf } from "@/lib/csrf";
import { encryptTotpSecret } from "@/lib/crypto";
import { prisma } from "@/lib/prisma";
import { getClientIp, getUserAgent } from "@/lib/request";
import { permissionSchema, sharedAccountSchema, totpSecretSchema } from "@/lib/validation";

export async function POST(request: NextRequest, context: { params: Promise<{ id: string }> }) {
  const actor = await requireAdmin();
  const { id } = await context.params;
  const formData = await request.formData();

  if (!verifyCsrf(request, formData)) {
    return NextResponse.json({ error: "Invalid request." }, { status: 403 });
  }

  const action = formData.get("_action")?.toString();
  const ipAddress = getClientIp(request);
  const userAgent = getUserAgent(request);

  if (action === "archive") {
    await prisma.sharedAccount.update({
      where: { id },
      data: { archivedAt: new Date(), isActive: false },
    });
    await logAuditEvent({
      actorId: actor.id,
      sharedAccountId: id,
      action: AuditAction.SHARED_ACCOUNT_ARCHIVED,
      ipAddress,
      userAgent,
    });
    return NextResponse.redirect(new URL("/admin/shared-accounts", request.url));
  }

  if (action === "disable") {
    await prisma.sharedAccount.update({ where: { id }, data: { isActive: false } });
    await logAuditEvent({
      actorId: actor.id,
      sharedAccountId: id,
      action: AuditAction.SHARED_ACCOUNT_DISABLED,
      ipAddress,
      userAgent,
    });
    return NextResponse.redirect(new URL(`/admin/shared-accounts/${id}`, request.url));
  }

  if (action === "add-totp") {
    const parsed = totpSecretSchema.safeParse(Object.fromEntries(formData));
    if (!parsed.success) {
      return NextResponse.redirect(new URL(`/admin/shared-accounts/${id}?error=totp`, request.url));
    }

    await prisma.totpSecret.upsert({
      where: { sharedAccountId: id },
      create: {
        sharedAccountId: id,
        ...encryptTotpSecret(parsed.data.secret),
      },
      update: encryptTotpSecret(parsed.data.secret),
    });

    await logAuditEvent({
      actorId: actor.id,
      sharedAccountId: id,
      action: AuditAction.TOTP_SECRET_ADDED,
      ipAddress,
      userAgent,
    });
    return NextResponse.redirect(new URL(`/admin/shared-accounts/${id}?updated=1`, request.url));
  }

  if (action === "grant") {
    const parsed = permissionSchema.safeParse(Object.fromEntries(formData));
    if (!parsed.success) {
      return NextResponse.redirect(
        new URL(`/admin/shared-accounts/${id}?error=permission`, request.url),
      );
    }

    await prisma.accountPermission.upsert({
      where: {
        userId_sharedAccountId: {
          userId: parsed.data.userId,
          sharedAccountId: id,
        },
      },
      create: {
        userId: parsed.data.userId,
        sharedAccountId: id,
        canViewCode: parsed.data.canViewCode,
      },
      update: {
        canViewCode: parsed.data.canViewCode,
      },
    });

    await logAuditEvent({
      actorId: actor.id,
      targetUserId: parsed.data.userId,
      sharedAccountId: id,
      action: AuditAction.ACCESS_GRANTED,
      ipAddress,
      userAgent,
      metadata: { canViewCode: parsed.data.canViewCode },
    });
    return NextResponse.redirect(new URL(`/admin/shared-accounts/${id}?updated=1`, request.url));
  }

  if (action === "revoke") {
    const userId = formData.get("userId")?.toString();
    if (userId) {
      await prisma.accountPermission.deleteMany({
        where: {
          userId,
          sharedAccountId: id,
        },
      });
      await logAuditEvent({
        actorId: actor.id,
        targetUserId: userId,
        sharedAccountId: id,
        action: AuditAction.ACCESS_REVOKED,
        ipAddress,
        userAgent,
      });
    }
    return NextResponse.redirect(new URL(`/admin/shared-accounts/${id}?updated=1`, request.url));
  }

  const parsed = sharedAccountSchema.safeParse(Object.fromEntries(formData));
  if (!parsed.success) {
    return NextResponse.redirect(new URL(`/admin/shared-accounts/${id}?error=invalid`, request.url));
  }

  await prisma.sharedAccount.update({
    where: { id },
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
    sharedAccountId: id,
    action: AuditAction.SHARED_ACCOUNT_UPDATED,
    ipAddress,
    userAgent,
  });

  return NextResponse.redirect(new URL(`/admin/shared-accounts/${id}?updated=1`, request.url));
}
