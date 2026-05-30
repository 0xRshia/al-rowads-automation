export function StatusMessage({ error }: Readonly<{ error?: string }>) {
  if (!error) {
    return null;
  }

  const messages: Record<string, string> = {
    invalid: "Please check the submitted values.",
    duplicate: "That email or username is already in use.",
    password: "The new password does not meet the password requirements.",
    totp: "The TOTP secret could not be saved.",
    permission: "The selected permission could not be saved.",
    rate_limited: "Too many attempts. Try again later.",
  };

  return (
    <p className="mb-4 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm font-semibold text-red-800">
      {messages[error] || "The request could not be completed."}
    </p>
  );
}
