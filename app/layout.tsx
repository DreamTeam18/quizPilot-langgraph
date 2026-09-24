import type { Metadata, Viewport } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "QuizPilot",
  description:
    "An adaptive quiz coach: a LangGraph orchestrator delegating to question and grading specialists.",
};

export const viewport: Viewport = {
  themeColor: "#f4f7fc",
  viewportFit: "cover",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
