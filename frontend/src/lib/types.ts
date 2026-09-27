// AI-assisted (OpenCode + Claude): TypeScript models mirroring the
// user-service and supplier-service API contracts. Reviewed by authors.

export type Role = "admin" | "client";

export const SUPPLIER_CATEGORIES = [
  "Food",
  "Food/Coffee",
  "Shopping",
  "Printing",
] as const;

export type Category = (typeof SUPPLIER_CATEGORIES)[number];

// ---- Supplier service (camelCase over the wire) ----
export interface Supplier {
  id: string;
  name: string;
  category: Category;
  building: string;
  floor?: string | null;
  locationDescription?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  startingTime?: string | null;
  closingTime?: string | null;
  imageUrl?: string | null;
  active: boolean;
}

export interface SupplierList {
  items: Supplier[];
  page: number;
  pageSize: number;
  total: number;
}

export interface SupplierCreate {
  name: string;
  category: Category;
  building: string;
  floor?: string | null;
  locationDescription?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  startingTime?: string | null;
  closingTime?: string | null;
  imageUrl?: string | null;
}

export type SupplierUpdate = Partial<SupplierCreate>;

export interface SupplierQuery {
  category?: Category[];
  zone?: string;
  q?: string;
  page?: number;
  pageSize?: number;
}

// ---- User service ----
export interface LoginResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
}

export interface RegisterResponse {
  id: string;
  email: string;
  message: string;
}

export interface ProfileResponse {
  id: string;
  email: string;
  display_name: string;
  contact_number: string | null;
  role: Role;
  email_verified: boolean;
}

export interface AdminUser {
  id: string;
  email: string;
  display_name: string;
  contact_number: string | null;
  role: Role;
  email_verified: boolean;
  is_suspended: boolean;
  created_at: string;
}

export interface AdminUserList {
  items: AdminUser[];
  total: number;
  limit: number;
  offset: number;
}
