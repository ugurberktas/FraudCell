import "./globals.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "FraudCell Golden Demo",
  description: "FraudCell role-based demo workspace",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="tr">
      <body>{children}</body>
    </html>
  );
}
