// AI-assisted (OpenCode + Claude): responsive supplier browse page with live
// search, category/zone filters, client-side sort and server pagination.
// Reviewed by authors.
import {
  Alert,
  Button,
  Center,
  Group,
  Loader,
  Pagination,
  SegmentedControl,
  Select,
  SimpleGrid,
  Stack,
  Text,
  TextInput,
  Title,
} from "@mantine/core";
import { useDebouncedValue } from "@mantine/hooks";
import { IconPlus, IconSearch } from "@tabler/icons-react";
import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { SupplierCard } from "../../components/SupplierCard";
import { ApiError, suppliersApi } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { SUPPLIER_CATEGORIES, type Category, type Supplier } from "../../lib/types";

const PAGE_SIZE = 12;

type SortKey = "name" | "category" | "building";

export default function SupplierList() {
  const { isAdmin } = useAuth();
  const navigate = useNavigate();

  const [q, setQ] = useState("");
  const [debouncedQ] = useDebouncedValue(q, 300);
  const [category, setCategory] = useState<Category | null>(null);
  const [zone, setZone] = useState("");
  const [debouncedZone] = useDebouncedValue(zone, 300);
  const [sort, setSort] = useState<SortKey>("name");
  const [page, setPage] = useState(1);

  const [items, setItems] = useState<Supplier[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Reset to first page whenever filters change.
  useEffect(() => {
    setPage(1);
  }, [debouncedQ, category, debouncedZone]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    suppliersApi
      .list({
        q: debouncedQ || undefined,
        category: category ? [category] : undefined,
        zone: debouncedZone || undefined,
        page,
        pageSize: PAGE_SIZE,
      })
      .then((res) => {
        if (cancelled) return;
        setItems(res.items);
        setTotal(res.total);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err instanceof ApiError ? err.message : "Failed to load suppliers");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [debouncedQ, category, debouncedZone, page]);

  // Client-side sort (the API has no sort param).
  const sortedItems = useMemo(() => {
    return [...items].sort((a, b) =>
      String(a[sort] ?? "").localeCompare(String(b[sort] ?? "")),
    );
  }, [items, sort]);

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <Stack gap="lg">
      <Group justify="space-between" align="flex-end" wrap="wrap">
        <div>
          <Title order={2}>Campus Suppliers</Title>
          <Text c="dimmed" size="sm">
            Browse vendors, stores and landmarks across campus
          </Text>
        </div>
        {isAdmin && (
          <Button
            leftSection={<IconPlus size={16} />}
            onClick={() => navigate("/admin/suppliers")}
          >
            Add supplier
          </Button>
        )}
      </Group>

      <Stack gap="sm">
        <Group grow wrap="wrap">
          <TextInput
            leftSection={<IconSearch size={16} />}
            placeholder="Search suppliers..."
            value={q}
            onChange={(e) => setQ(e.currentTarget.value)}
          />
          <Select
            placeholder="All categories"
            clearable
            data={SUPPLIER_CATEGORIES.map((c) => ({ value: c, label: c }))}
            value={category}
            onChange={(v) => setCategory(v as Category | null)}
          />
          <TextInput
            placeholder="Filter by building / zone"
            value={zone}
            onChange={(e) => setZone(e.currentTarget.value)}
          />
        </Group>
        <Group justify="space-between" wrap="wrap">
          <Text size="sm" c="dimmed">
            {total} supplier{total === 1 ? "" : "s"}
          </Text>
          <Group gap="xs">
            <Text size="sm" c="dimmed">
              Sort by
            </Text>
            <SegmentedControl
              size="xs"
              value={sort}
              onChange={(v) => setSort(v as SortKey)}
              data={[
                { label: "Name", value: "name" },
                { label: "Category", value: "category" },
                { label: "Building", value: "building" },
              ]}
            />
          </Group>
        </Group>
      </Stack>

      {error && (
        <Alert color="red" title="Error">
          {error}
        </Alert>
      )}

      {loading ? (
        <Center h={200}>
          <Loader />
        </Center>
      ) : sortedItems.length === 0 ? (
        <Center h={160}>
          <Text c="dimmed">No suppliers match your filters.</Text>
        </Center>
      ) : (
        <SimpleGrid cols={{ base: 1, sm: 2, md: 3 }} spacing="md">
          {sortedItems.map((s) => (
            <SupplierCard key={s.id} supplier={s} />
          ))}
        </SimpleGrid>
      )}

      {totalPages > 1 && (
        <Group justify="center" mt="sm">
          <Pagination value={page} onChange={setPage} total={totalPages} />
        </Group>
      )}
    </Stack>
  );
}
