import { NextResponse, type NextRequest } from "next/server";
import { Prisma } from "@prisma/client";
import { AuditAction, logAuditEvent } from "@/lib/audit";
import { requireAdmin } from "@/lib/auth";
import { verifyCsrf } from "@/lib/csrf";
import { hashPassword } from "@/lib/password";
import { prisma } from "@/lib/prisma";
import { getClientIp, getUserAgent } from "@/lib/request";
import { resetPasswordSchema, updateUserSchema } from "@/lib/validation";

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

  if (action === "disable") {
    await prisma.user.update({ where: { id }, data: { isActive: false } });
    await logAuditEvent({
      actorId: actor.id,
      targetUserId: id,
      action: AuditAction.USER_DISABLED,
      ipAddress,
      userAgent,
    });
    return NextResponse.redirect(new URL(`/admin/employees/${id}`, request.url));
  }

  if (action === "delete") {
    await prisma.user.update({ where: { id }, data: { isActive: false, deletedAt: new Date() } });
    await logAuditEvent({
      actorId: actor.id,
      targetUserId: id,
      action: AuditAction.USER_SOFT_DELETED,
      ipAddress,
      userAgent,
    });
    return NextResponse.redirect(new URL("/admin/employees", request.url));
  }

  if (action === "reset-password") {
    const parsed = resetPasswordSchema.safeParse(Object.fromEntries(formData));
    if (!parsed.success) {
      return NextResponse.redirect(new URL(`/admin/employees/${id}?error=password`, request.url));
    }
    await prisma.user.update({
      where: { id },
      data: { passwordHash: await hashPassword(parsed.data.password) },
    });
    await logAuditEvent({
      actorId: actor.id,
      targetUserId: id,
      action: AuditAction.USER_PASSWORD_RESET,
      ipAddress,
      userAgent,
    });
    return NextResponse.redirect(new URL(`/admin/employees/${id}?updated=1`, request.url));
  }

  const parsed = updateUserSchema.safeParse(Object.fromEntries(formData));
  if (!parsed.success) {
    return NextResponse.redirect(new URL(`/admin/employees/${id}?error=invalid`, request.url));
  }

  try {
    const user = await prisma.user.update({
      where: { id },
      data: parsed.data,
    });
    await logAuditEvent({
      actorId: actor.id,
      targetUserId: id,
      action: AuditAction.USER_UPDATED,
      ipAddress,
      userAgent,
      metadata: { role: user.role, isActive: user.isActive },
    });
    return NextResponse.redirect(new URL(`/admin/employees/${id}?updated=1`, request.url));
  } catch (error) {
    if (error instanceof Prisma.PrismaClientKnownRequestError && error.code === "P2002") {
      return NextResponse.redirect(new URL(`/admin/employees/${id}?error=duplicate`, request.url));
    }
    throw error;
  }
}
