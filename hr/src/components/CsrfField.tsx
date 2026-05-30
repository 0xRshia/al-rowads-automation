"use client";

import { useEffect, useState } from "react";
import { CSRF_COOKIE_NAME, CSRF_FIELD_NAME } from "@/lib/csrf";

function readCookie(name: string): string {
  const prefix = `${name}=`;
  return document.cookie
    .split(";")
    .map((part) => part.trim())
    .find((part) => part.startsWith(prefix))
    ?.slice(prefix.length) || "";
}

export function CsrfField() {
  const [token, setToken] = useState("");

  useEffect(() => {
    setToken(readCookie(CSRF_COOKIE_NAME));
  }, []);

  return <input type="hidden" name={CSRF_FIELD_NAME} value={token} />;
}
