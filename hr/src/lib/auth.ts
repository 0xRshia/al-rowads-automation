import crypto from "node:crypto";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import type { UserRole } from "@prisma/client";
import { prisma } from "@/lib/prisma";
import { canAccessAdmin, canAccessEmployeeApp, isAdminRole } from "@/lib/authorization";

export const SESSION_COOKIE_NAME = "hr_session";
const SESSION_TTL_SECONDS = 60 * 60 * 8;

type SessionPayload = {
  userId: string;
  role: UserRole;
  expiresAt: number;
};

function getSessionSecret(): string {
  const secret = process.env.SESSION_SECRET;
  if (secret && secret.length >= 32) {
    return secret;
  }

  if (process.env.NODE_ENV !== "production") {
    return "development-session-secret-change-before-production";
  }

  throw new Error("SESSION_SECRET must be at least 32 characters in production.");
}

function sign(payload: string): string {
  return crypto.createHmac("sha256", getSessionSecret()).update(payload).digest("base64url");
}

function encodeSession(payload: SessionPayload): string {
  const body = Buffer.from(JSON.stringify(payload), "utf8").toString("base64url");
  return `${body}.${sign(body)}`;
}

function decodeSession(value?: string): SessionPayload | null {
  if (!value) {
    return null;
  }

  const [body, signature] = value.split(".");
  if (!body || !signature || sign(body) !== signature) {
    return null;
  }

  try {
    const payload = JSON.parse(Buffer.from(body, "base64url").toString("utf8")) as SessionPayload;
    if (!payload.userId || payload.expiresAt <= Math.floor(Date.now() / 1000)) {
      return null;
    }
    return payload;
  } catch {
    return null;
  }
}

export async function createSession(user: { id: string; role: UserRole }): Promise<void> {
  const cookieStore = await cookies();
  cookieStore.set(
    SESSION_COOKIE_NAME,
    encodeSession({
      userId: user.id,
      role: user.role,
      expiresAt: Math.floor(Date.now() / 1000) + SESSION_TTL_SECONDS,
    }),
    {
      httpOnly: true,
      sameSite: "lax",
      secure: process.env.NODE_ENV === "production",
      path: "/",
      maxAge: SESSION_TTL_SECONDS,
    },
  );
}

export async function clearSession(): Promise<void> {
  (await cookies()).set(SESSION_COOKIE_NAME, "", {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: 0,
  });
}

export async function getCurrentUser() {
  const cookieStore = await cookies();
  const session = decodeSession(cookieStore.get(SESSION_COOKIE_NAME)?.value);
  if (!session) {
    return null;
  }

  return prisma.user.findFirst({
    where: {
      id: session.userId,
      isActive: true,
      deletedAt: null,
    },
  });
}

export async function requireUser() {
  const user = await getCurrentUser();
  if (!user || !canAccessEmployeeApp(user)) {
    redirect("/login");
  }
  return user;
}

export async function requireAdmin() {
  const user = await getCurrentUser();
  if (!user || !canAccessAdmin(user)) {
    redirect("/login");
  }
  return user;
}

export function destinationForRole(role: UserRole): string {
  return isAdminRole(role) ? "/admin/dashboard" : "/app/dashboard";
}
