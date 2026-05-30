import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "HR Admin Panel",
  description: "Internal HR and shared account access panel",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
