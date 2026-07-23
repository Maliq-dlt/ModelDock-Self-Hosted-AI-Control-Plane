import type { Metadata } from "next";
import { Nav } from "../components/nav";
import "./globals.css";

export const metadata: Metadata = { title: "ModelDock", description: "Self-hosted AI control plane" };

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body><div className="shell"><Nav /><main>{children}</main></div></body></html>;
}
