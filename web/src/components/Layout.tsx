import { Link, NavLink, Outlet } from "react-router-dom";
import { t } from "../i18n/en";

const tabs = [
  { to: "/", label: t.nav.home, icon: "M3 11l9-8 9 8v9a1 1 0 0 1-1 1h-5v-6h-6v6H4a1 1 0 0 1-1-1z" },
  { to: "/list", label: t.nav.list, icon: "M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01" },
  { to: "/compare", label: t.nav.compare, icon: "M11 4a7 7 0 1 0 0 14 7 7 0 0 0 0-14zm10 17-5-5" },
  { to: "/add-price", label: t.nav.addPrice, icon: "M12 5v14M5 12h14" },
  { to: "/account", label: t.nav.account, icon: "M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8zm-8 9a8 8 0 0 1 16 0" },
];

export default function Layout() {
  return (
    <div className="mx-auto flex min-h-dvh max-w-2xl flex-col">
      <a href="#main" className="sr-only focus:not-sr-only focus:p-2">Skip to content</a>
      <header className="flex items-center justify-between px-4 pt-4 pb-2">
        <Link to="/" className="text-lg font-bold text-brand-700 dark:text-brand-100">{t.appName}</Link>
        <span className="rounded-full bg-brand-50 px-3 py-1 text-xs font-semibold text-brand-800 dark:bg-brand-800/30 dark:text-brand-100">
          {t.betaBadge}
        </span>
      </header>

      <main id="main" className="flex-1 space-y-4 px-4 pb-28">
        <Outlet />
        <footer className="space-y-2 pt-6 text-xs text-slate-500 dark:text-slate-400">
          <nav aria-label="Legal" className="flex gap-4">
            <Link to="/legal/privacy" className="underline">{t.legal.privacy}</Link>
            <Link to="/legal/terms" className="underline">{t.legal.terms}</Link>
            <Link to="/legal/pricing" className="underline">{t.legal.pricing}</Link>
          </nav>
          <p>{t.legal.attribution}</p>
        </footer>
      </main>

      <nav
        aria-label="Main"
        className="fixed inset-x-0 bottom-0 border-t border-slate-200 bg-white/95 pb-[env(safe-area-inset-bottom)] backdrop-blur dark:border-slate-800 dark:bg-slate-950/95"
      >
        <ul className="mx-auto grid max-w-2xl grid-cols-5">
          {tabs.map((tab) => (
            <li key={tab.to}>
              <NavLink
                to={tab.to}
                end={tab.to === "/"}
                className={({ isActive }) =>
                  `flex min-h-14 flex-col items-center justify-center gap-0.5 text-xs font-medium ${
                    isActive ? "text-brand-700 dark:text-brand-100" : "text-slate-500 dark:text-slate-400"
                  }`
                }
              >
                <svg viewBox="0 0 24 24" className="h-6 w-6" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden>
                  <path d={tab.icon} />
                </svg>
                {tab.label}
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>
    </div>
  );
}
