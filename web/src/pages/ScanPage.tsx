import { useEffect, useRef, useState, type FormEvent } from "react";
import { api, type BarcodeResult } from "../lib/api";
import { formatFreshness, formatPrice } from "../lib/format";
import { t } from "../i18n/en";
import { Button, Card, Notice, PageTitle, TextInput } from "../components/ui";

interface DetectedBarcode { rawValue: string }
interface BarcodeDetectorLike { detect(source: HTMLVideoElement): Promise<DetectedBarcode[]> }
declare global {
  interface Window { BarcodeDetector?: new (opts: { formats: string[] }) => BarcodeDetectorLike }
}

export default function ScanPage() {
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const [scanning, setScanning] = useState(false);
  const [code, setCode] = useState("");
  const [result, setResult] = useState<BarcodeResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const supported = typeof window !== "undefined" && !!window.BarcodeDetector && !!navigator.mediaDevices;

  const stop = () => {
    streamRef.current?.getTracks().forEach((tr) => tr.stop());
    streamRef.current = null;
    setScanning(false);
  };
  useEffect(() => stop, []);

  async function lookup(barcode: string) {
    setError(null);
    try {
      setResult(await api<BarcodeResult>(`/api/barcode/lookup?barcode=${encodeURIComponent(barcode)}`));
    } catch (err) {
      setError((err as Error).message || t.errors.generic);
    }
  }

  async function start() {
    if (!window.BarcodeDetector) return;
    const detector = new window.BarcodeDetector({ formats: ["ean_13", "ean_8", "upc_a", "upc_e"] });
    const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" } });
    streamRef.current = stream;
    setScanning(true);
    const video = videoRef.current!;
    video.srcObject = stream;
    await video.play();
    const tick = async () => {
      if (!streamRef.current) return;
      const found = await detector.detect(video).catch(() => []);
      if (found.length) {
        stop();
        setCode(found[0].rawValue);
        lookup(found[0].rawValue);
      } else {
        requestAnimationFrame(tick);
      }
    };
    tick();
  }

  function onManual(e: FormEvent) {
    e.preventDefault();
    if (code.trim()) lookup(code.trim());
  }

  return (
    <>
      <PageTitle>{t.scan.title}</PageTitle>
      {supported ? (
        <Card className="space-y-3">
          <video ref={videoRef} className={`w-full rounded-xl bg-black ${scanning ? "" : "hidden"}`} muted playsInline />
          <Button onClick={scanning ? stop : start} className="w-full">{scanning ? t.scan.stop : t.scan.start}</Button>
        </Card>
      ) : (
        <Notice>{t.scan.unsupported}</Notice>
      )}

      <form onSubmit={onManual} className="flex items-end gap-2">
        <div className="flex-1">
          <TextInput id="barcode" label={t.scan.manual} inputMode="numeric" value={code} onChange={(e) => setCode(e.target.value)} />
        </div>
        <Button type="submit">{t.scan.lookup}</Button>
      </form>

      {error && <Notice tone="error">{error}</Notice>}
      {result && !result.found && <Notice>{result.message ?? t.scan.notFound}</Notice>}
      {result?.found && (
        <Card className="space-y-3">
          <div className="flex gap-3">
            {result.image_url && <img src={result.image_url} alt="" className="h-20 w-20 rounded-lg object-contain" />}
            <div>
              <h2 className="font-bold">{result.name}</h2>
              <p className="text-sm text-slate-500">{[result.brand, result.package_size].filter(Boolean).join(" · ")}</p>
            </div>
          </div>
          {result.store_prices && result.store_prices.length > 0 ? (
            <ul className="divide-y divide-slate-200 dark:divide-slate-800">
              {result.store_prices.map((sp) => (
                <li key={sp.store_id} className="flex justify-between py-2">
                  <span>
                    {sp.store_name}
                    <span className="block text-xs text-slate-500">{t.compare.reports(sp.observation_count)} · {formatFreshness(sp.last_observed_at)}</span>
                  </span>
                  <span className="font-bold">{formatPrice(sp.price)}</span>
                </li>
              ))}
            </ul>
          ) : (
            <Notice>{t.scan.noPrices}</Notice>
          )}
          {result.nutrition && result.nutrition.calories != null && (
            <p className="text-sm text-slate-600 dark:text-slate-400">{result.nutrition.calories} kcal {t.scan.per100g}</p>
          )}
          {result.attribution && <p className="text-xs text-slate-500">{result.attribution}</p>}
        </Card>
      )}
    </>
  );
}
