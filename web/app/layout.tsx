import type { Metadata } from "next";
import type { ReactNode } from "react";
import { Plus_Jakarta_Sans, JetBrains_Mono } from "next/font/google";
import "./globals.css";

// Plus Jakarta Sans = display + UI voice; JetBrains Mono = measured numbers.
const ui = Plus_Jakarta_Sans({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-ui",
});
const num = JetBrains_Mono({
  subsets: ["latin"],
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
