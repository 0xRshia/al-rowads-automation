import { describe, expect, it } from "vitest";
import { canAccessAdmin, canViewSharedAccount, canViewTotpCode } from "@/lib/authorization";

const activeUser = { isActive: true, deletedAt: null };
const activeAccount = { isActive: true, archivedAt: null };

describe("authorization boundaries", () => {
  it("only active admins can access admin pages", () => {
    expect(canAccessAdmin({ ...activeUser, role: "SUPER_ADMIN" })).toBe(true);
    expect(canAccessAdmin({ ...activeUser, role: "HR_ADMIN" })).toBe(true);
    expect(canAccessAdmin({ ...activeUser, role: "MANAGER" })).toBe(false);
    expect(canAccessAdmin({ ...activeUser, role: "EMPLOYEE" })).toBe(false);
    expect(canAccessAdmin({ role: "SUPER_ADMIN", isActive: false, deletedAt: null })).toBe(false);
    expect(canAccessAdmin({ role: "SUPER_ADMIN", isActive: true, deletedAt: new Date() })).toBe(false);
  });

  it("requires an explicit active-account permission to view a shared account", () => {
    expect(canViewSharedAccount(activeUser, activeAccount, { userId: "user_1" })).toBe(true);
    expect(canViewSharedAccount(activeUser, activeAccount, null)).toBe(false);
    expect(canViewSharedAccount(activeUser, { isActive: false, archivedAt: null }, { userId: "user_1" })).toBe(
      false,
    );
    expect(
      canViewSharedAccount(activeUser, { isActive: true, archivedAt: new Date() }, { userId: "user_1" }),
    ).toBe(false);
  });

  it("requires canViewCode to view current TOTP codes", () => {
    expect(canViewTotpCode(activeUser, activeAccount, { userId: "user_1", canViewCode: true })).toBe(true);
    expect(canViewTotpCode(activeUser, activeAccount, { userId: "user_1", canViewCode: false })).toBe(false);
    expect(canViewTotpCode({ isActive: false, deletedAt: null }, activeAccount, { userId: "user_1", canViewCode: true })).toBe(
      false,
    );
  });
});
