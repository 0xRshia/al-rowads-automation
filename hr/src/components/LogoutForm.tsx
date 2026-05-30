import { CsrfField } from "@/components/CsrfField";

export function LogoutForm() {
  return (
    <form action="/api/auth/logout" method="post">
      <CsrfField />
      <button className="btn btn-secondary" type="submit">
        Log out
      </button>
    </form>
  );
}
