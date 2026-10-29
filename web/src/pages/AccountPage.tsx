import { useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { api, type Profile } from "../lib/api";
import { useAuth } from "../lib/auth";
import { supabase } from "../lib/supabase";
import { t } from "../i18n/en";
import { Button, Card, Notice, PageTitle, TextInput } from "../components/ui";

function SignIn() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function send(e: FormEvent) {
    e.preventDefault();
    setError(null);
    const { error: err } = await supabase!.auth.signInWithOtp({ email, options: { emailRedirectTo: window.location.origin + "/account" } });
    if (err) setError(err.message);
    else setSent(true);
  }

  return (
    <Card>
      <h2 className="mb-3 font-bold">{t.account.signInTitle}</h2>
      {sent ? <Notice tone="success">{t.account.linkSent}</Notice> : (
        <form onSubmit={send} className="space-y-3">
          <TextInput id="email" type="email" label={t.account.emailLabel} required autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} />
          <Button type="submit" className="w-full">{t.account.sendLink}</Button>
          <p className="text-xs text-slate-500">
            <Link to="/legal/terms" className="underline">{t.legal.terms}</Link> · <Link to="/legal/privacy" className="underline">{t.legal.privacy}</Link>
          </p>
        </form>
      )}
      {error && <div className="mt-3"><Notice tone="error">{error}</Notice></div>}
    </Card>
  );
}

function ProfilePanel() {
  const [profile, setProfile] = useState<Profile | null>(null);
  const [name, setName] = useState("");
  const [marketing, setMarketing] = useState(false);
  const [status, setStatus] = useState<string | null>(null);

  useEffect(() => {
    api<Profile>("/api/me").then((p) => {
      setProfile(p);
      setName(p.display_name ?? "");
      setMarketing(p.marketing_opt_in);
    }).catch((e: Error) => setStatus(e.message));
  }, []);

  async function save(e: FormEvent) {
    e.preventDefault();
    const p = await api<Profile>("/api/me", { method: "PATCH", body: JSON.stringify({ display_name: name, marketing_opt_in: marketing }) });
    setProfile({ ...profile!, ...p });
    setStatus(t.account.saved);
  }

  async function exportData() {
    const data = await api<unknown>("/api/me/export");
    const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }));
    const a = Object.assign(document.createElement("a"), { href: url, download: "smartcart-my-data.json" });
    a.click();
    URL.revokeObjectURL(url);
  }

  async function deleteAccount() {
    if (!window.confirm(t.account.deleteConfirm)) return;
    await api("/api/me", { method: "DELETE" });
    await supabase!.auth.signOut();
    setStatus(t.account.deleted);
  }

  if (!profile) return status ? (
    <div className="space-y-3">
      <Notice tone="error">{status}</Notice>
      <Button variant="secondary" onClick={() => supabase!.auth.signOut()}>{t.account.signOut}</Button>
    </div>
  ) : null;

  return (
    <>
      {profile.is_admin && (
        <Card className="flex items-center justify-between gap-3">
          <span className="rounded-full bg-brand-50 px-3 py-1 text-xs font-semibold text-brand-800">{t.admin.badge}</span>
          <Link to="/admin" className="font-semibold text-brand-700 underline dark:text-brand-100">{t.admin.open}</Link>
        </Card>
      )}
      <Card>
        <p className="mb-3 text-sm text-slate-600 dark:text-slate-400">{profile.email}</p>
        <form onSubmit={save} className="space-y-3">
          <TextInput id="display-name" label={t.account.displayName} value={name} maxLength={80} onChange={(e) => setName(e.target.value)} />
          <label className="flex items-start gap-2 text-sm">
            <input type="checkbox" className="mt-1" checked={marketing} onChange={(e) => setMarketing(e.target.checked)} />
            {t.account.marketing}
          </label>
          <Button type="submit">{t.account.save}</Button>
        </form>
        {status && <div className="mt-3"><Notice tone="success">{status}</Notice></div>}
      </Card>
      <Card className="space-y-2">
        <p className="text-sm">{t.account.myReports}: <strong>{profile.price_reports}</strong></p>
        <div className="flex flex-wrap gap-2">
          <Button variant="secondary" onClick={exportData}>{t.account.export}</Button>
          <Button variant="secondary" onClick={() => supabase!.auth.signOut()}>{t.account.signOut}</Button>
          <Button variant="danger" onClick={deleteAccount}>{t.account.delete}</Button>
        </div>
      </Card>
    </>
  );
}

export default function AccountPage() {
  const { enabled, session, loading } = useAuth();
  return (
    <>
      <PageTitle>{t.account.title}</PageTitle>
      {!enabled && <Notice>{t.account.unavailable}</Notice>}
      {enabled && !loading && (session ? <ProfilePanel /> : <SignIn />)}
    </>
  );
}
