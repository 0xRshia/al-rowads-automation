import { z } from "zod";

const strongPassword = z
  .string()
  .min(10)
  .regex(/[a-z]/, "Password must include a lowercase letter.")
  .regex(/[A-Z]/, "Password must include an uppercase letter.")
  .regex(/[0-9]/, "Password must include a number.");

export const loginSchema = z.object({
  identifier: z.string().trim().min(1).max(255),
  password: z.string().min(1).max(256),
});

export const createUserSchema = z.object({
  fullName: z.string().trim().min(2).max(120),
  email: z.string().trim().email().max(255).transform((value) => value.toLowerCase()),
  username: z.string().trim().min(3).max(60).regex(/^[a-zA-Z0-9_.-]+$/),
  password: strongPassword,
  role: z.enum(["SUPER_ADMIN", "HR_ADMIN", "MANAGER", "EMPLOYEE"]),
  isActive: z.coerce.boolean().optional().default(true),
});

export const updateUserSchema = createUserSchema
  .omit({ password: true })
  .extend({
    isActive: z.coerce.boolean().optional().default(false),
  });

export const resetPasswordSchema = z.object({
  password: strongPassword,
});

export const sharedAccountSchema = z.object({
  serviceName: z.string().trim().min(2).max(120),
  accountLabel: z.string().trim().min(2).max(120),
  loginEmail: z.string().trim().email().max(255).transform((value) => value.toLowerCase()),
  notes: z.string().trim().max(2000).optional().or(z.literal("")),
  isActive: z.coerce.boolean().optional().default(false),
});

export const totpSecretSchema = z.object({
  secret: z.string().trim().min(8).max(256),
});

export const permissionSchema = z.object({
  userId: z.string().min(1),
  canViewCode: z.coerce.boolean().optional().default(false),
});
