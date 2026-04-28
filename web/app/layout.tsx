import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "OpsCanvas",
  description: "Agent runs, traces, and spans.",
  icons: {
    icon: "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='6' fill='%23101113'/%3E%3Crect x='1' y='1' width='30' height='30' rx='5' fill='none' stroke='%23ffffff' stroke-opacity='0.085'/%3E%3Ctext x='16' y='21' fill='%238ba2fb' font-family='ui-monospace,Menlo,monospace' font-size='12' font-weight='600' text-anchor='middle' letter-spacing='-0.5'%3EOC%3C/text%3E%3C/svg%3E",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script
          dangerouslySetInnerHTML={{
            __html:
              "try{var t=localStorage.getItem('opscanvas-theme');if(t!=='light'&&t!=='dark'){t=matchMedia('(prefers-color-scheme: light)').matches?'light':'dark'}document.documentElement.dataset.theme=t}catch(e){document.documentElement.dataset.theme='dark'}",
          }}
        />
      </head>
      <body>{children}</body>
    </html>
  );
}
