import { afterEach, describe, expect, it } from "vitest";
import { decryptTotpSecret, encryptTotpSecret } from "@/lib/crypto";

const previousKey = process.env.TOTP_ENCRYPTION_KEY;

afterEach(() => {
  process.env.TOTP_ENCRYPTION_KEY = previousKey;
});

describe("TOTP secret encryption", () => {
  it("round trips secrets with AES-256-GCM fields", () => {
    process.env.TOTP_ENCRYPTION_KEY = Buffer.alloc(32, 7).toString("base64");

    const encrypted = encryptTotpSecret("JBSWY3DPEHPK3PXP");

    expect(encrypted.encryptedSecret).not.toContain("JBSWY3DPEHPK3PXP");
    expect(encrypted.iv).toBeTruthy();
    expect(encrypted.authTag).toBeTruthy();
    expect(decryptTotpSecret(encrypted)).toBe("JBSWY3DPEHPK3PXP");
  });
});
