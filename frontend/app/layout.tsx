import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Ask-N-Seek — Natural Language Video Retrieval",
  description: "Type what happened, we'll show you exactly where — and prove it.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="bg-black text-cream-100 antialiased">{children}</body>
    </html>
  );
}
