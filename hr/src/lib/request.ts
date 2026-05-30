import type { NextRequest } from "next/server";

export function getClientIp(request: Request | NextRequest): string {
  const forwardedFor = request.headers.get("x-forwarded-for");
  if (forwardedFor) {
    return forwardedFor.split(",")[0]?.trim() || "unknown";
  }

  return request.headers.get("x-real-ip") || "unknown";
}

export function getUserAgent(request: Request | NextRequest): string {
  return request.headers.get("user-agent") || "unknown";
}

export function sameOrigin(request: Request | NextRequest): boolean {
  const host = request.headers.get("host");
  const origin = request.headers.get("origin");
  const referer = request.headers.get("referer");

  if (!host) {
    return false;
  }

  const expectedHttp = `http://${host}`;
  const expectedHttps = `https://${host}`;
  const source = origin || referer;

  if (!source) {
    return false;
  }

  return source.startsWith(expectedHttp) || source.startsWith(expectedHttps);
}
