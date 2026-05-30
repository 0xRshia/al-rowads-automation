import type { AccountPermission, SharedAccount, User, UserRole } from "@prisma/client";

export const ADMIN_ROLES: UserRole[] = ["SUPER_ADMIN", "HR_ADMIN"];

export function isAdminRole(role: UserRole): boolean {
  return ADMIN_ROLES.includes(role);
}

export function canAccessAdmin(user: Pick<User, "role" | "isActive" | "deletedAt">): boolean {
  return user.isActive && !user.deletedAt && isAdminRole(user.role);
}

export function canAccessEmployeeApp(
  user: Pick<User, "isActive" | "deletedAt">,
): boolean {
  return user.isActive && !user.deletedAt;
}

export function canViewSharedAccount(
  user: Pick<User, "isActive" | "deletedAt">,
  account: Pick<SharedAccount, "isActive" | "archivedAt">,
  permission?: Pick<AccountPermission, "userId"> | null,
): boolean {
  return canAccessEmployeeApp(user) && account.isActive && !account.archivedAt && Boolean(permission);
}

export function canViewTotpCode(
  user: Pick<User, "isActive" | "deletedAt">,
  account: Pick<SharedAccount, "isActive" | "archivedAt">,
  permission?: Pick<AccountPermission, "userId" | "canViewCode"> | null,
): boolean {
  return canViewSharedAccount(user, account, permission) && permission?.canViewCode === true;
}
