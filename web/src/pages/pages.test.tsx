import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";
import App from "../App";
import { saveList, saveLocation } from "../lib/storage";

type Handler = (url: string, init?: RequestInit) => unknown;

function mockFetch(handler: Handler) {
  const fn = vi.fn(async (url: string, init?: RequestInit) => {
    const body = handler(url, init);
    return new Response(JSON.stringify(body ?? {}), { status: 200, headers: { "Content-Type": "application/json" } });
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

const renderAt = (path: string) => render(<MemoryRouter initialEntries={[path]}><App /></MemoryRouter>);

afterEach(() => vi.unstubAllGlobals());

describe("Home", () => {
  it("shows real coverage numbers and saves a valid postal code", async () => {
    mockFetch((url) => {
      if (url.includes("/api/coverage/stats")) return { total_stores_tracked: 208, stores_with_prices: 3 };
      if (url.includes("/api/geocode")) return { status: "ok", postal_code: "T6E 2A1", neighborhood: "Old Strathcona" };
    });
    renderAt("/");
    expect(await screen.findByText(/208 Edmonton-area stores · 3 with recent prices/)).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Your postal code"), "t6e2a1");
    await userEvent.click(screen.getByRole("button", { name: "Set location" }));
    expect(await screen.findByText(/Showing stores near T6E 2A1 \(Old Strathcona\)/)).toBeInTheDocument();
    expect(JSON.parse(localStorage.getItem("sc.location.v1")!)).toEqual({ postalCode: "T6E 2A1", area: "Old Strathcona" });
  });

  it("rejects an invalid postal code without calling the API", async () => {
    const fetchFn = mockFetch(() => ({ total_stores_tracked: 0, stores_with_prices: 0 }));
    renderAt("/");
    await userEvent.type(screen.getByLabelText("Your postal code"), "12345");
    await userEvent.click(screen.getByRole("button", { name: "Set location" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Edmonton-area postal code");
    expect(fetchFn.mock.calls.some(([u]) => String(u).includes("/api/geocode"))).toBe(false);
  });
});

describe("Shopping list", () => {
  it("adds, persists and removes items", async () => {
    mockFetch(() => ({}));
    renderAt("/list");
    await userEvent.type(screen.getByLabelText("Item, e.g. eggs"), "eggs");
    await userEvent.click(screen.getByRole("button", { name: "Add" }));
    expect(screen.getByText("eggs")).toBeInTheDocument();
    expect(JSON.parse(localStorage.getItem("sc.list.v1")!)).toHaveLength(1);
    await userEvent.click(screen.getByRole("button", { name: "Remove eggs" }));
    expect(screen.getByText(/Your list is empty/)).toBeInTheDocument();
  });
});

describe("Plan", () => {
  it("explains when there isn't enough price data instead of showing empty plans", async () => {
    saveLocation({ postalCode: "T6E 2A1", area: "" });
    saveList([{ id: "1", name: "butter", quantity: 1 }]);
    mockFetch(() => ({
      plans: { plan_1_split: null, plan_2_single: null, plan_3_stock: null },
      unmatched_items: [],
      notice: { code: "insufficient_price_data", message: "We don't have recent prices for these items." },
    }));
    renderAt("/plan");
    expect(await screen.findByText("Not enough price data yet.")).toBeInTheDocument();
    expect(screen.getByText(/We don't have recent prices/)).toBeInTheDocument();
  });

  it("renders plan totals and directions", async () => {
    saveLocation({ postalCode: "T6E 2A1", area: "" });
    saveList([{ id: "1", name: "butter", quantity: 1 }]);
    const plan = {
      grocery_cost: 5.49, gas_cost: 0.42, all_in_cost: 5.91, total_distance_km: 3, drive_time_minutes: 6,
      full_route_directions_url: "https://maps.example/r",
      stores: [{ store_name: "No Frills", chain: "No Frills", address: "", store_subtotal: 5.49, directions_url: "https://maps.example/s",
        items: [{ item_name: "Salted Butter", requested: "butter", packages: 1, total_cost: 5.49, store_name: "No Frills" }] }],
    };
    mockFetch(() => ({ plans: { plan_1_split: plan, plan_2_single: null, plan_3_stock: null }, unmatched_items: [] }));
    renderAt("/plan");
    expect(await screen.findByText("Lowest total")).toBeInTheDocument();
    expect(screen.getByText("$5.91")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Directions" })).toHaveAttribute("href", "https://maps.example/s");
  });
});

describe("Compare", () => {
  it("shows how many reports back each price and how fresh it is", async () => {
    saveLocation({ postalCode: "T6E 2A1", area: "" });
    mockFetch(() => ({
      data: [{ product_id: 8, name: "Salted Butter", standard_package: "454 g", stores: [
        { store_id: 1, store_name: "No Frills", banner: "No Frills", distance_km: 1.2, price: 5.49, unit_price_display: "$1.21/100g",
          is_lowest: true, is_on_sale: false, observation_count: 3, last_observed_at: new Date().toISOString(), flyer_deal: null },
      ] }],
    }));
    renderAt("/compare");
    await userEvent.type(screen.getByRole("searchbox"), "butter");
    await userEvent.click(screen.getByRole("button", { name: "Search" }));
    expect(await screen.findByText("Salted Butter")).toBeInTheDocument();
    expect(screen.getByText(/3 reports · today/)).toBeInTheDocument();
  });
});

describe("Accounts disabled", () => {
  it("says accounts aren't available when Supabase isn't configured", async () => {
    mockFetch(() => ({}));
    renderAt("/add-price");
    await waitFor(() => expect(screen.getByText("Accounts aren't available yet.")).toBeInTheDocument());
  });
});

describe("Legal pages", () => {
  it("renders the privacy policy draft", () => {
    mockFetch(() => ({}));
    renderAt("/legal/privacy");
    expect(screen.getByRole("heading", { name: "Privacy Policy" })).toBeInTheDocument();
  });
});
