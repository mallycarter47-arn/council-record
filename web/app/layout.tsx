import type { Metadata } from "next";
import { Barlow_Condensed, IBM_Plex_Mono, Source_Serif_4 } from "next/font/google";
import "./globals.css";

// Self-hosted at build time by next/font, so the demo runs with wifi off.
const display = Barlow_Condensed({
  variable: "--font-display",
  subsets: ["latin"],
  weight: ["500", "600", "700"],
});
const serif = Source_Serif_4({
  variable: "--font-serif",
  subsets: ["latin"],
  weight: ["400", "600"],
});
const mono = IBM_Plex_Mono({
  variable: "--font-mono",
  subsets: ["latin"],
  weight: ["400", "500"],
});

export const metadata: Metadata = {
  title: "Council Record",
  description:
    "Search what Detroit City Council actually did. Every result links to the official record.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${display.variable} ${serif.variable} ${mono.variable}`}>
      <body>{children}</body>
    </html>
  );
}
