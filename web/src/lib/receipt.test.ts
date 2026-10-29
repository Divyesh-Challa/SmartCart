import { parseReceiptText } from "./receipt";

describe("parseReceiptText", () => {
  it("keeps item lines and skips totals, taxes and payments", () => {
    const text = [
      "NO FRILLS #1234",
      "06038318 SALTED BUTTER 454G   5.49 MRJ",
      "LARGE EGGS 12PK          4.29",
      "BANANAS 1.23 kg @ $1.52/kg 1.87",
      "2 @ 1.99",
      "SUBTOTAL                 11.65",
      "GST                       0.27",
      "TOTAL                    11.92",
      "VISA                     11.92",
      "PC POINTS EARNED          120",
    ].join("\n");
    expect(parseReceiptText(text)).toEqual([
      { name: "SALTED BUTTER 454G", price: 5.49 },
      { name: "LARGE EGGS 12PK", price: 4.29 },
      { name: "BANANAS", price: 1.87 },
    ]);
  });

  it("reads comma decimals and ignores discounts", () => {
    expect(parseReceiptText("BREAD 675G 2.99 MR]")).toEqual([{ name: "BREAD 675G", price: 2.99 }]);
    expect(parseReceiptText("MILK 2L 4,79\nINSTANT SAVINGS -1.00\nBREAD -0.50")).toEqual([{ name: "MILK 2L", price: 4.79 }]);
  });
});
