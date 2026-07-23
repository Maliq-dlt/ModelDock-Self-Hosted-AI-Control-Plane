"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const groups = [
  {
    label: "Workspace",
    links: [
      ["Home", "/", "HM"],
      ["Providers", "/providers", "PV"],
      ["Routing", "/routing", "RT"],
      ["Usage", "/usage", "US"],
      ["Quota", "/budgets", "QT"],
    ],
  },
  {
    label: "Tools",
    links: [
      ["Token Saver", "/token-saver", "TS"],
      ["API Keys", "/keys", "AK"],
      ["CLI Tools", "/cli-tools", "CL"],
    ],
  },
  {
    label: "System",
    links: [
      ["Models", "/models", "MD"],
      ["Traces", "/traces", "TR"],
      ["Settings", "/settings", "ST"],
    ],
  },
] as const;

export function Nav() {
  const pathname = usePathname();

  return (
    <aside className="sidebar">
      <div className="brandBlock">
        <Link href="/" className="brand">
          <span className="brandGlyph"><i />MD</span>
          <span><strong>ModelDock</strong><small>AI control plane</small></span>
        </Link>
        <span className="versionTag">self-hosted</span>
      </div>

      <nav aria-label="Primary navigation">
        {groups.map((group) => (
          <div className="navGroup" key={group.label}>
            <p>{group.label}</p>
            {group.links.map(([label, href, mark]) => {
              const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
              return (
                <Link key={href} href={href} className={active ? "active" : ""}>
                  <span className="navMark">{mark}</span>
                  <span>{label}</span>
                  <i />
                </Link>
              );
            })}
          </div>
        ))}
      </nav>

      <div className="sidebarFooter">
        <Link href="/manage" className="setupButton"><span>+</span> Setup center</Link>
        <div className="gatewayStatus">
          <span className="liveDot" />
          <div><strong>Local gateway</strong><small>localhost:8080/v1</small></div>
        </div>
        <span className="footerNote">Secrets stay server-side</span>
      </div>
    </aside>
  );
}
