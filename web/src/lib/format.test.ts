import { formatFreshness, formatPrice, normalizePostalCode } from "./format";

describe("formatPrice", () => {
  it("formats CAD and shows a dash for missing prices", () => {
    expect(formatPrice(5.5)).toBe("$5.50");
    expect(formatPrice(null)).toBe("—");
  });
});

describe("formatFreshness", () => {
  const now = new Date("2026-10-28T15:00:00");
  it("describes how old a price is", () => {
    expect(formatFreshness("2026-10-28T08:00:00", now)).toBe("today");
    expect(formatFreshness("2026-10-27T20:00:00", now)).toBe("yesterday");
    expect(formatFreshness("2026-10-20T12:00:00", now)).toBe("8 days ago");
  });
  it("handles missing or invalid dates", () => {
    expect(formatFreshness(null, now)).toBe("date unknown");
    expect(formatFreshness("not a date", now)).toBe("date unknown");
  });
});

describe("normalizePostalCode", () => {
  it("accepts valid codes in any spacing or case", () => {
    expect(normalizePostalCode("t6e2a1")).toBe("T6E 2A1");
    expect(normalizePostalCode(" T5K 2X4 ")).toBe("T5K 2X4");
  });
  it("rejects invalid codes", () => {
    expect(normalizePostalCode("12345")).toBeNull();
    expect(normalizePostalCode("D6E 2A1")).toBeNull();
  });
});
