import Link from "next/link";
import { AdminShell } from "@/components/AdminShell";
import { requireAdmin } from "@/lib/auth";
import { prisma } from "@/lib/prisma";

export default async function EmployeesPage() {
  await requireAdmin();
  const users = await prisma.user.findMany({
    where: { deletedAt: null },
    orderBy: { createdAt: "desc" },
  });

  return (
    <AdminShell title="Employees">
      <div className="mb-4 flex justify-end">
        <Link className="btn btn-primary" href="/admin/employees/new">
          New employee
        </Link>
      </div>
      <div className="panel overflow-x-auto">
        <table className="w-full min-w-[720px] text-left text-sm">
          <thead className="bg-slate-100 text-slate-600">
            <tr>
              <th className="px-4 py-3">Name</th>
              <th className="px-4 py-3">Email</th>
              <th className="px-4 py-3">Username</th>
              <th className="px-4 py-3">Role</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3">Last login</th>
            </tr>
          </thead>
          <tbody>
            {users.map((user) => (
              <tr className="border-t border-slate-200" key={user.id}>
                <td className="px-4 py-3 font-semibold">
                  <Link className="text-blue-800" href={`/admin/employees/${user.id}`}>
                    {user.fullName}
                  </Link>
                </td>
                <td className="px-4 py-3">{user.email}</td>
                <td className="px-4 py-3">{user.username}</td>
                <td className="px-4 py-3">{user.role}</td>
                <td className="px-4 py-3">{user.isActive ? "Active" : "Disabled"}</td>
                <td className="px-4 py-3">
                  {user.lastLoginAt ? user.lastLoginAt.toLocaleString() : "Never"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </AdminShell>
  );
}
