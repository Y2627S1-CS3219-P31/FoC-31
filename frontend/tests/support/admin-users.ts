// AI-assisted (GitHub Copilot Chat, DeepSeek V4.1 Flash): admin user fixtures
// used by the admin portal regression tests. Reviewed by authors.
import type { AdminUser } from "../../src/lib/types";

export function makeAdminUser(overrides: Partial<AdminUser> = {}): AdminUser {
  return {
    id: "user-1",
    email: "e0123456@u.nus.edu",
    display_name: "Ada Lovelace",
    contact_number: null,
    role: "client",
    email_verified: true,
    is_suspended: false,
    created_at: "2026-01-15T08:00:00Z",
    ...overrides,
  };
}

export function adminUserList(
  items: AdminUser[],
  {
    total = items.length,
    limit = 20,
    offset = 0,
  }: { total?: number; limit?: number; offset?: number } = {},
) {
  return { items, total, limit, offset };
}
