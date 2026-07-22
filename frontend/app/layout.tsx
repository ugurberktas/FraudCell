import "./globals.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "FraudCell Platform Status",
  description: "Real-time microservice status dashboard for FraudCell",
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
