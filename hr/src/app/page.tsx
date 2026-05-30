import { redirect } from "next/navigation";
import { getCurrentUser, destinationForRole } from "@/lib/auth";

export default async function HomePage() {
  const user = await getCurrentUser();
  redirect(user ? destinationForRole(user.role) : "/login");
}
