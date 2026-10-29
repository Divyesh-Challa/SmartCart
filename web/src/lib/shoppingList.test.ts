import { mergeLists } from "./shoppingList";

const item = (id: string, name: string, quantity = 1) => ({ id, name, quantity });

describe("mergeLists", () => {
  it("keeps the account's list and adds device-only items", () => {
    const server = [item("s1", "Eggs", 2)];
    const local = [item("l1", "eggs"), item("l2", "Butter")];
    expect(mergeLists(server, local)).toEqual([item("s1", "Eggs", 2), item("l2", "Butter")]);
  });

  it("uses the device list when the account has none", () => {
    const local = [item("l1", "Milk")];
    expect(mergeLists([], local)).toEqual(local);
  });
});
