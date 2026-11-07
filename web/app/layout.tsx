import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";
import localFont from "next/font/local";
import { Providers } from "./providers";
import "@/styles/tokens.css";
import "@/styles/base.css";
import "./globals.css";

const ui = localFont({
  src: "./fonts/PlusJakartaSans-latin.woff2",
  weight: "200 800",
  style: "normal",
  display: "swap",
  variable: "--font-ui",
});

const num = localFont({
  src: "./fonts/JetBrainsMono-latin.woff2",
  weight: "100 800",
  style: "normal",
  display: "swap",
  variable: "--font-num",
});

export const metadata: Metadata = {
  metadataBase: new URL(process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000"),
  title: {
    default: "ParkWise | Parking Occupancy Intelligence",
    template: "%s | ParkWise",
  },
  description: "Measured per-bay parking occupancy and vehicle tracking from real camera footage.",
  openGraph: {
    type: "website",
    siteName: "ParkWise",
    title: "ParkWise | Parking Occupancy Intelligence",
    description: "Measured per-bay parking occupancy from real video.",
  },
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#F7F8FA" },
    { media: "(prefers-color-scheme: dark)", color: "#0E1116" },
  ],
};

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="en" className={`${ui.variable} ${num.variable}`} suppressHydrationWarning>
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
