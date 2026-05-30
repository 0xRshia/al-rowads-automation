import crypto from "node:crypto";

type EncryptedSecret = {
  encryptedSecret: string;
  iv: string;
  authTag: string;
};

function getEncryptionKey(): Buffer {
  const value = process.env.TOTP_ENCRYPTION_KEY;
  if (!value) {
    throw new Error("TOTP_ENCRYPTION_KEY is required to encrypt TOTP secrets.");
  }

  const base64 = Buffer.from(value, "base64");
  if (base64.length === 32) {
    return base64;
  }

  const hex = Buffer.from(value, "hex");
  if (hex.length === 32) {
    return hex;
  }

  const utf8 = Buffer.from(value, "utf8");
  if (utf8.length === 32) {
    return utf8;
  }

  throw new Error("TOTP_ENCRYPTION_KEY must resolve to exactly 32 bytes.");
}

export function encryptTotpSecret(secret: string): EncryptedSecret {
  const iv = crypto.randomBytes(12);
  const cipher = crypto.createCipheriv("aes-256-gcm", getEncryptionKey(), iv);
  const encrypted = Buffer.concat([cipher.update(secret, "utf8"), cipher.final()]);

  return {
    encryptedSecret: encrypted.toString("base64"),
    iv: iv.toString("base64"),
    authTag: cipher.getAuthTag().toString("base64"),
  };
}

export function decryptTotpSecret(encrypted: EncryptedSecret): string {
  const decipher = crypto.createDecipheriv(
    "aes-256-gcm",
    getEncryptionKey(),
    Buffer.from(encrypted.iv, "base64"),
  );
  decipher.setAuthTag(Buffer.from(encrypted.authTag, "base64"));

  const decrypted = Buffer.concat([
    decipher.update(Buffer.from(encrypted.encryptedSecret, "base64")),
    decipher.final(),
  ]);

  return decrypted.toString("utf8");
}
