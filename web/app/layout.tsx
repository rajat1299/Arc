import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Arc OpsCanvas",
  description: "Trace operations workspace",
  icons: {
    icon: "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='7' fill='%2308090a'/%3E%3Cpath d='M9 23 15.2 8h1.6L23 23h-2.3l-1.4-3.5h-6.6L11.3 23H9Zm4.5-5.5h5L16 11.2l-2.5 6.3Z' fill='%237170ff'/%3E%3C/svg%3E",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
