import { AdminShell } from "@/components/AdminShell";
import { requireAdmin } from "@/lib/auth";
import { prisma } from "@/lib/prisma";

export default async function AuditLogsPage() {
  await requireAdmin();
  const logs = await prisma.auditLog.findMany({
    include: { actor: true, sharedAccount: true },
    orderBy: { createdAt: "desc" },
    take: 100,
  });

  return (
    <AdminShell title="Audit Logs">
      <div className="panel overflow-x-auto">
        <table className="w-full min-w-[920px] text-left text-sm">
          <thead className="bg-slate-100 text-slate-600">
            <tr>
              <th className="px-4 py-3">Created</th>
              <th className="px-4 py-3">Action</th>
              <th className="px-4 py-3">Actor</th>
              <th className="px-4 py-3">Shared account</th>
              <th className="px-4 py-3">IP</th>
              <th className="px-4 py-3">Metadata</th>
            </tr>
          </thead>
          <tbody>
            {logs.map((log) => (
              <tr className="border-t border-slate-200 align-top" key={log.id}>
                <td className="px-4 py-3">{log.createdAt.toLocaleString()}</td>
                <td className="px-4 py-3 font-semibold">{log.action}</td>
                <td className="px-4 py-3">{log.actor?.email || "System"}</td>
                <td className="px-4 py-3">{log.sharedAccount?.serviceName || ""}</td>
                <td className="px-4 py-3">{log.ipAddress || ""}</td>
                <td className="px-4 py-3 font-mono text-xs">
                  {log.metadata ? JSON.stringify(log.metadata) : ""}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </AdminShell>
  );
}
