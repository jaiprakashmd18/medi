import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";

import { AppShell } from "@/components/layout/AppShell";

import "./globals.css";

export const metadata: Metadata = {
  title: { default: "MEDI-GENIUS", template: "%s · MEDI-GENIUS" },
  description: "AI-powered medical education platform that teaches from your own study materials.",
};

export const viewport: Viewport = { themeColor: "#030814", width: "device-width", initialScale: 1 };

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body><AppShell>{children}</AppShell></body>
    </html>
  );
}
