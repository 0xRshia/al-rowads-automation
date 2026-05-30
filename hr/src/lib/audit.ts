import type { Prisma } from "@prisma/client";
import { prisma } from "@/lib/prisma";

export const AuditAction = {
  USER_LOGIN_SUCCESS: "USER_LOGIN_SUCCESS",
  USER_LOGIN_FAILED: "USER_LOGIN_FAILED",
  USER_CREATED: "USER_CREATED",
  USER_DISABLED: "USER_DISABLED",
  USER_UPDATED: "USER_UPDATED",
  USER_PASSWORD_RESET: "USER_PASSWORD_RESET",
  USER_SOFT_DELETED: "USER_SOFT_DELETED",
  SHARED_ACCOUNT_CREATED: "SHARED_ACCOUNT_CREATED",
  SHARED_ACCOUNT_UPDATED: "SHARED_ACCOUNT_UPDATED",
  SHARED_ACCOUNT_DISABLED: "SHARED_ACCOUNT_DISABLED",
  SHARED_ACCOUNT_ARCHIVED: "SHARED_ACCOUNT_ARCHIVED",
  TOTP_SECRET_ADDED: "TOTP_SECRET_ADDED",
  TOTP_CODE_VIEWED: "TOTP_CODE_VIEWED",
  ACCESS_GRANTED: "ACCESS_GRANTED",
  ACCESS_REVOKED: "ACCESS_REVOKED",
} as const;

export type AuditActionName = (typeof AuditAction)[keyof typeof AuditAction];

export async function logAuditEvent(input: {
  actorId?: string | null;
  sharedAccountId?: string | null;
  targetUserId?: string | null;
  action: AuditActionName;
  ipAddress?: string | null;
  userAgent?: string | null;
  metadata?: Prisma.InputJsonValue;
}): Promise<void> {
  await prisma.auditLog.create({
    data: {
      actorId: input.actorId ?? null,
      sharedAccountId: input.sharedAccountId ?? null,
      targetUserId: input.targetUserId ?? null,
      action: input.action,
      ipAddress: input.ipAddress ?? null,
      userAgent: input.userAgent ?? null,
      metadata: input.metadata ?? undefined,
    },
  });
}
