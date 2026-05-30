import { NextResponse, type NextRequest } from "next/server";
import { clearSession } from "@/lib/auth";
import { verifyCsrf } from "@/lib/csrf";

export async function POST(request: NextRequest) {
  const formData = await request.formData();
  if (!verifyCsrf(request, formData)) {
    return NextResponse.json({ error: "Invalid request." }, { status: 403 });
  }

  await clearSession();
  return NextResponse.redirect(new URL("/login", request.url));
}
