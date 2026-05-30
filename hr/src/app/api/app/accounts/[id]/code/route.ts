import { NextResponse, type NextRequest } from "next/server";
import { AuditAction, logAuditEvent } from "@/lib/audit";
import { requireUser } from "@/lib/auth";
import { canViewTotpCode } from "@/lib/authorization";
import { generateCurrentTotpCode } from "@/lib/totp";
import { prisma } from "@/lib/prisma";
import { checkRateLimit } from "@/lib/rate-limit";
import { getClientIp, getUserAgent } from "@/lib/request";

export async function GET(request: NextRequest, context: { params: Promise<{ id: string }> }) {
  const user = await requireUser();
  const { id } = await context.params;
  const ipAddress = getClientIp(request);
  const limit = checkRateLimit(`code:${user.id}:${id}:${ipAddress}`, {
    limit: 30,
    windowMs: 60 * 1000,
  });

  if (!limit.allowed) {
    return NextResponse.json(
      { error: "Too many code requests.", retryAfterSeconds: limit.retryAfterSeconds },
      { status: 429 },
    );
  }

  const permission = await prisma.accountPermission.findUnique({
    where: {
      userId_sharedAccountId: {
        userId: user.id,
        sharedAccountId: id,
      },
    },
    include: {
      sharedAccount: {
        include: {
          totpSecret: true,
        },
      },
    },
  });

  const account = permission?.sharedAccount;
  if (!permission || !account || !canViewTotpCode(user, account, permission)) {
    return NextResponse.json({ error: "Not authorized." }, { status: 403 });
  }

  if (!account.totpSecret) {
    return NextResponse.json({ error: "No TOTP secret configured." }, { status: 404 });
  }

  const result = generateCurrentTotpCode(account.totpSecret);
  await logAuditEvent({
    actorId: user.id,
    sharedAccountId: id,
    action: AuditAction.TOTP_CODE_VIEWED,
    ipAddress,
    userAgent: getUserAgent(request),
  });

  return NextResponse.json(result, {
    headers: {
      "Cache-Control": "no-store",
    },
  });
}
