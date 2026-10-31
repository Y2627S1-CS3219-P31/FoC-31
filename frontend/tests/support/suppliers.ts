// AI-assisted (GitHub Copilot Chat, DeepSeek V4.1 Flash): supplier fixtures used
// by the supplier regression tests. Reviewed by authors.
import type { Supplier } from "../../src/lib/types";

export function makeSupplier(overrides: Partial<Supplier> = {}): Supplier {
  return {
    id: "sup-1",
    name: "Coffee Bean",
    category: "Food/Coffee",
    building: "COM3",
    floor: "Level 1",
    locationDescription: "Near the entrance",
    latitude: 1.2940156,
    longitude: 103.7738478,
    startingTime: "08:00",
    closingTime: "20:00",
    imageUrl: null,
    active: true,
    ...overrides,
  };
}

export function supplierList(
  items: Supplier[],
  {
    page = 1,
    pageSize = 12,
    total = items.length,
  }: { page?: number; pageSize?: number; total?: number } = {},
) {
  return { items, page, pageSize, total };
}
