import { authenticator } from "otplib";
import { decryptTotpSecret } from "@/lib/crypto";

export function generateCurrentTotpCode(encrypted: {
  encryptedSecret: string;
  iv: string;
  authTag: string;
}): { code: string; secondsRemaining: number } {
  const secret = decryptTotpSecret(encrypted);
  const code = authenticator.generate(secret);
  const step = authenticator.options.step ?? 30;
  const secondsRemaining = step - (Math.floor(Date.now() / 1000) % step);

  return { code, secondsRemaining };
}
