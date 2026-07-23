"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const groups = [
  { label: "Command", links: [["Overview", "/", "⌁"], ["Providers", "/providers", "◫"], ["Models", "/models", "◇"], ["Traces", "/traces", "↯"]] },
  { label: "Control", links: [["Budgets", "/budgets", "◎"], ["Manage", "/manage", "＋"]] },
];

export function Nav() {
  const pathname = usePathname();
  return <aside className="sidebar"><div className="brandBlock"><Link href="/" className="brand"><span className="brandGlyph"><i />MD</span><span><strong>ModelDock</strong><small>AI control plane</small></span></Link><span className="versionTag">v0.3 edge</span></div><nav>{groups.map(group => <div className="navGroup" key={group.label}><p>{group.label}</p>{group.links.map(([label, href, icon]) => { const active = href === "/" ? pathname === "/" : pathname.startsWith(href); return <Link key={href} href={href} className={active ? "active" : ""}><span className="navIcon">{icon}</span>{label}<i /></Link>; })}</div>)}</nav><div className="sidebarFooter"><div className="gatewayStatus"><span className="liveDot" /><div><strong>Gateway online</strong><small>localhost:8080/v1</small></div></div><div className="footerRule" /><span className="footerNote">Self-hosted · credentials sealed</span></div></aside>;
}
