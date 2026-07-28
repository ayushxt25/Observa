import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "PulseGrid",
  description: "High-performance real-time telemetry dashboard",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}
