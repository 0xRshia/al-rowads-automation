import { PrismaClient } from "@prisma/client";
import { encryptTotpSecret } from "../src/lib/crypto";
import { hashPassword } from "../src/lib/password";

const prisma = new PrismaClient();

async function main() {
  const passwordHash = await hashPassword("ChangeMe123!");

  const superAdmin = await prisma.user.upsert({
    where: { email: "admin@example.com" },
    update: {},
    create: {
      fullName: "Super Admin",
      email: "admin@example.com",
      username: "admin",
      passwordHash,
      role: "SUPER_ADMIN",
    },
  });

  const employee = await prisma.user.upsert({
    where: { email: "employee@example.com" },
    update: {},
    create: {
      fullName: "Example Employee",
      email: "employee@example.com",
      username: "employee",
      passwordHash,
      role: "EMPLOYEE",
    },
  });

  const account = await prisma.sharedAccount.create({
    data: {
      serviceName: "ChatGPT",
      accountLabel: "Company workspace",
      loginEmail: "shared-chatgpt@example.com",
      notes: "Seed account for local development.",
      isActive: true,
    },
  });

  await prisma.accountPermission.upsert({
    where: {
      userId_sharedAccountId: {
        userId: employee.id,
        sharedAccountId: account.id,
      },
    },
    update: { canViewCode: true },
    create: {
      userId: employee.id,
      sharedAccountId: account.id,
      canViewCode: true,
    },
  });

  if (process.env.TOTP_ENCRYPTION_KEY) {
    await prisma.totpSecret.upsert({
      where: { sharedAccountId: account.id },
      create: {
        sharedAccountId: account.id,
        ...encryptTotpSecret("JBSWY3DPEHPK3PXP"),
      },
      update: encryptTotpSecret("JBSWY3DPEHPK3PXP"),
    });
  }

  await prisma.auditLog.create({
    data: {
      actorId: superAdmin.id,
      sharedAccountId: account.id,
      action: "SHARED_ACCOUNT_CREATED",
      metadata: { seed: true },
    },
  });

  console.log("Seed complete.");
  console.log("Admin: admin@example.com / ChangeMe123!");
  console.log("Employee: employee@example.com / ChangeMe123!");
}

main()
  .catch((error) => {
    console.error(error);
    process.exit(1);
  })
  .finally(async () => {
    await prisma.$disconnect();
  });
