import { cookies } from "next/headers";
import type { NextRequest } from "next/server";
import { sameOrigin } from "@/lib/request";

export const CSRF_COOKIE_NAME = "hr_csrf_token";
export const CSRF_FIELD_NAME = "csrfToken";

export async function getCsrfToken(): Promise<string> {
  return (await cookies()).get(CSRF_COOKIE_NAME)?.value || "";
}

export function verifyCsrf(request: NextRequest, formData?: FormData): boolean {
  if (!sameOrigin(request)) {
    return false;
  }

  const cookieToken = request.cookies.get(CSRF_COOKIE_NAME)?.value;
  const submittedToken =
    request.headers.get("x-csrf-token") || formData?.get(CSRF_FIELD_NAME)?.toString();

  if (!cookieToken && !submittedToken) {
    return true;
  }

  return Boolean(cookieToken && submittedToken && cookieToken === submittedToken);
}
