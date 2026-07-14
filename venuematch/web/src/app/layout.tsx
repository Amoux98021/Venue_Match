import "@fontsource-variable/manrope";
import "@fontsource-variable/newsreader";
import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "VenueMatch | Booking intelligence",
  description: "Transparent artist and venue recommendations powered by local demand and booking history.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
