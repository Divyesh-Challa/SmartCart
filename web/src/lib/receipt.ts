// Receipt photos are read on the device (Tesseract.js); only the lines the
// shopper confirms are sent, as ordinary price reports. The image never leaves the phone.

export interface ReceiptLine {
  name: string;
  price: number;
}

// Lines that carry a price but aren't an item.
const NON_ITEM = /\b(sub-?total|total|tax|gst|pst|hst|balance|change|cash|visa|master ?card|debit|amex|tender|savings?|you saved|points|deposit|rounding|discount|coupon|refund|tip)\b/i;
// Trailing tax flags (e.g. "MRJ", "H") are often misread by OCR as brackets or pipes.
const PRICE_AT_END = /^(.*?)[\s.:$]*?\$?\s*(-?\d{1,4}[.,]\d{2})\s*-?\s*[A-Z*\][|()]{0,3}$/;

function cleanName(raw: string): string {
  return raw
    .split(/\s@\s|\s\d+[.,]\d+\s*(?:kg|lb)\b/i)[0] // drop "2 @ 1.99" and weighed amounts like "1.23 kg"
    .replace(/^\d{4,}\s+/, "") // leading product / PLU codes
    .replace(/\s+/g, " ")
    .trim();
}

/** Picks "item ... price" lines out of OCR text, skipping totals, taxes, payments and discounts. */
export function parseReceiptText(text: string): ReceiptLine[] {
  const lines: ReceiptLine[] = [];
  for (const rawLine of text.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || NON_ITEM.test(line)) continue;
    const m = PRICE_AT_END.exec(line);
    if (!m) continue;
    const price = Number(m[2].replace(",", "."));
    const name = cleanName(m[1]);
    if (!(price > 0) || (name.match(/[a-z]/gi)?.length ?? 0) < 3) continue;
    lines.push({ name, price });
  }
  return lines;
}

/** Runs OCR on a photo in the browser. Tesseract (and its language data) loads only when first used. */
export async function readReceipt(image: File, onProgress?: (fraction: number) => void): Promise<ReceiptLine[]> {
  const { createWorker } = await import("tesseract.js");
  const worker = await createWorker("eng", 1, {
    logger: (m: { status: string; progress: number }) => {
      if (m.status === "recognizing text") onProgress?.(m.progress);
    },
  });
  try {
    const { data } = await worker.recognize(image);
    return parseReceiptText(data.text);
  } finally {
    await worker.terminate();
  }
}
