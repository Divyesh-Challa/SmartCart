import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode } from "react";

export function PageTitle({ children }: { children: ReactNode }) {
  return <h1 className="text-2xl font-bold tracking-tight">{children}</h1>;
}

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <section className={`rounded-2xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-800 dark:bg-slate-900 ${className}`}>
      {children}
    </section>
  );
}

export function Button({ variant = "primary", className = "", ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "danger" }) {
  const styles = {
    primary: "bg-brand-700 text-white hover:bg-brand-800 disabled:bg-slate-400",
    secondary: "border border-slate-300 bg-white text-slate-800 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100",
    danger: "bg-red-700 text-white hover:bg-red-800",
  }[variant];
  return <button className={`min-h-11 rounded-xl px-4 font-semibold disabled:cursor-not-allowed ${styles} ${className}`} {...props} />;
}

export function TextInput({ label, id, ...props }: InputHTMLAttributes<HTMLInputElement> & { label: string; id: string }) {
  return (
    <label htmlFor={id} className="block">
      <span className="mb-1 block text-sm font-medium text-slate-700 dark:text-slate-300">{label}</span>
      <input
        id={id}
        className="min-h-11 w-full rounded-xl border border-slate-300 bg-white px-3 text-base dark:border-slate-700 dark:bg-slate-900"
        {...props}
      />
    </label>
  );
}

export function Notice({ tone = "info", children }: { tone?: "info" | "error" | "success"; children: ReactNode }) {
  const styles = {
    info: "bg-slate-100 text-slate-800 dark:bg-slate-800 dark:text-slate-100",
    error: "bg-red-50 text-red-800 dark:bg-red-950 dark:text-red-200",
    success: "bg-brand-50 text-brand-800 dark:bg-brand-800/30 dark:text-brand-100",
  }[tone];
  return (
    <p role={tone === "error" ? "alert" : "status"} className={`rounded-xl p-3 text-sm ${styles}`}>
      {children}
    </p>
  );
}

export function Spinner({ label }: { label: string }) {
  return (
    <p role="status" className="flex items-center gap-2 text-sm text-slate-600 dark:text-slate-400">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-brand-600 border-t-transparent" aria-hidden />
      {label}
    </p>
  );
}
