import { NextResponse, type NextRequest } from "next/server";
import { AuditAction, logAuditEvent } from "@/lib/audit";
import { createSession, destinationForRole } from "@/lib/auth";
import { verifyCsrf } from "@/lib/csrf";
import { verifyPassword } from "@/lib/password";
import { prisma } from "@/lib/prisma";
import { checkRateLimit, resetRateLimit } from "@/lib/rate-limit";
import { getClientIp, getUserAgent } from "@/lib/request";
import { loginSchema } from "@/lib/validation";

export async function POST(request: NextRequest) {
  const formData = await request.formData();
  const ipAddress = getClientIp(request);
  const userAgent = getUserAgent(request);

  if (!verifyCsrf(request, formData)) {
    return NextResponse.json({ error: "Invalid request." }, { status: 403 });
  }

  const parsed = loginSchema.safeParse(Object.fromEntries(formData));
  if (!parsed.success) {
    return NextResponse.redirect(new URL("/login?error=invalid", request.url));
  }

  const identifier = parsed.data.identifier.toLowerCase();
  const rateKey = `login:${ipAddress}:${identifier}`;
  const limit = checkRateLimit(rateKey, { limit: 5, windowMs: 15 * 60 * 1000 });

  if (!limit.allowed) {
    await logAuditEvent({
      action: AuditAction.USER_LOGIN_FAILED,
      ipAddress,
      userAgent,
      metadata: { identifier, reason: "rate_limited" },
    });
    return NextResponse.redirect(new URL("/login?error=rate_limited", request.url));
  }

  const user = await prisma.user.findFirst({
    where: {
      OR: [{ email: identifier }, { username: parsed.data.identifier }],
      deletedAt: null,
    },
  });

  const validPassword = user
    ? await verifyPassword(parsed.data.password, user.passwordHash)
    : false;

  if (!user || !user.isActive || !validPassword) {
    await logAuditEvent({
      actorId: user?.id,
      action: AuditAction.USER_LOGIN_FAILED,
      ipAddress,
      userAgent,
      metadata: {
        identifier,
        reason: !user ? "unknown_user" : !user.isActive ? "disabled_user" : "bad_password",
      },
    });
    return NextResponse.redirect(new URL("/login?error=invalid", request.url));
  }

  await prisma.user.update({
    where: { id: user.id },
    data: { lastLoginAt: new Date() },
  });
  await createSession(user);
  resetRateLimit(rateKey);
  await logAuditEvent({
    actorId: user.id,
    action: AuditAction.USER_LOGIN_SUCCESS,
    ipAddress,
    userAgent,
  });

  return NextResponse.redirect(new URL(destinationForRole(user.role), request.url));
}
