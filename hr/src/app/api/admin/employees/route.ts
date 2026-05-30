import { NextResponse, type NextRequest } from "next/server";
import { Prisma } from "@prisma/client";
import { AuditAction, logAuditEvent } from "@/lib/audit";
import { requireAdmin } from "@/lib/auth";
import { verifyCsrf } from "@/lib/csrf";
import { hashPassword } from "@/lib/password";
import { prisma } from "@/lib/prisma";
import { getClientIp, getUserAgent } from "@/lib/request";
import { createUserSchema } from "@/lib/validation";

export async function POST(request: NextRequest) {
  const actor = await requireAdmin();
  const formData = await request.formData();

  if (!verifyCsrf(request, formData)) {
    return NextResponse.json({ error: "Invalid request." }, { status: 403 });
  }

  const parsed = createUserSchema.safeParse(Object.fromEntries(formData));
  if (!parsed.success) {
    return NextResponse.redirect(new URL("/admin/employees/new?error=invalid", request.url));
  }

  try {
    const user = await prisma.user.create({
      data: {
        fullName: parsed.data.fullName,
        email: parsed.data.email,
        username: parsed.data.username,
        passwordHash: await hashPassword(parsed.data.password),
        role: parsed.data.role,
        isActive: parsed.data.isActive,
      },
    });

    await logAuditEvent({
      actorId: actor.id,
      targetUserId: user.id,
      action: AuditAction.USER_CREATED,
      ipAddress: getClientIp(request),
      userAgent: getUserAgent(request),
      metadata: { role: user.role },
    });

    return NextResponse.redirect(new URL(`/admin/employees/${user.id}`, request.url));
  } catch (error) {
    if (error instanceof Prisma.PrismaClientKnownRequestError && error.code === "P2002") {
      return NextResponse.redirect(new URL("/admin/employees/new?error=duplicate", request.url));
    }
    throw error;
  }
}
