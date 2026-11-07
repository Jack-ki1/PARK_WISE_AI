import type { Metadata } from "next";
import type { ReactNode } from "react";
import localFont from "next/font/local";
import "./globals.css";

// Self-hosted fonts (C0.5): `next/font/google` fetches from Google at build
// time, which breaks air-gapped/offline builds. The woff2 files under ./fonts
// are the latin subsets of Plus Jakarta Sans and JetBrains Mono, both licensed
// under the SIL Open Font License 1.1 and redistributable.
// Plus Jakarta Sans = display + UI voice; JetBrains Mono = measured numbers.
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
  title: "ParkWise AI | Parking Intelligence",
  description: "Real video-based parking analytics and occupancy intelligence.",
};

// Applies the stored theme before first paint so the dashboard never flashes.
// No stored choice defaults to the bright light theme.
const themeBootstrap = `try{var s=localStorage.getItem("parkwise-theme");var t=s==="light"||s==="dark"?s:"light";document.documentElement.dataset.theme=t;}catch(e){document.documentElement.dataset.theme="light";}`;

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="en" className={`${ui.variable} ${num.variable}`} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeBootstrap }} />
      </head>
      <body>{children}</body>
    </html>
  );
}
