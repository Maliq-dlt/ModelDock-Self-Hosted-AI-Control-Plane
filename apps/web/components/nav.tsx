import Link from "next/link";

const links = [
  ["Overview", "/"],
  ["Providers", "/providers"],
  ["Models", "/models"],
  ["Traces", "/traces"],
  ["Budgets", "/budgets"],
  ["Manage", "/manage"],
];

export function Nav() {
  return (
    <aside className="sidebar">
      <Link href="/" className="brand"><span>MD</span> ModelDock</Link>
      <nav>{links.map(([label, href]) => <Link key={href} href={href}>{label}</Link>)}</nav>
      <div className="sidebarFooter"><strong>Gateway</strong><span>localhost:8080/v1</span></div>
    </aside>
  );
}
