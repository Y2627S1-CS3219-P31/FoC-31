// AI-assisted: browse available errands page with reward filters, sort, and accept action.
import {
  Badge,
  Box,
  Button,
  Card,
  Group,
  Loader,
  NumberInput,
  Select,
  SimpleGrid,
  Stack,
  Text,
  TextInput,
  Title,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { OrderStatusBadge } from "../../components/StatusPill";
import { ApiError, type OrderResponse, ordersApi, parseUtcDate, suppliersApi } from "../../lib/api";

export default function BrowseErrands() {
  const navigate = useNavigate();

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [items, setItems] = useState<OrderResponse[]>([]);
  const [supplierNames, setSupplierNames] = useState<Record<string, string>>({});
  const [minReward, setMinReward] = useState<number | "">("");
  const [maxReward, setMaxReward] = useState<number | "">("");
  const [category, setCategory] = useState("");
  const [sortBy, setSortBy] = useState("deadline");
  const [sortOrder, setSortOrder] = useState("asc");

  useEffect(() => {
    suppliersApi
      .list({ includeInactive: false })
      .then((res) => {
        const map: Record<string, string> = {};
        for (const s of res.items) map[s.id] = s.name;
        setSupplierNames(map);
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    ordersApi
      .list({
        category: category ? [category] : undefined,
        min_reward: minReward || undefined,
        max_reward: maxReward || undefined,
        sort_by: sortBy,
        sort_order: sortOrder,
      })
      .then((res) => {
        if (cancelled) return;
        setItems(res);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err instanceof ApiError ? err.message : "Failed to load errands");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [category, minReward, maxReward, sortBy, sortOrder]);

  async function handleAccept(orderId: string) {
    try {
      await ordersApi.accept(orderId);
      window.dispatchEvent(new Event("credits-changed"));
      navigate("/deliveries");
    } catch (err) {
      notifications.show({
        color: "red",
        title: "Failed",
        message:
          err instanceof ApiError ? err.message : "Could not accept errand",
      });
    }
  }

  return (
    <Stack gap="lg">
      <Title order={2}>Browse Errands</Title>

      <Group wrap="wrap">
        <TextInput
          placeholder="Category"
          value={category}
          onChange={(e) => setCategory(e.currentTarget.value)}
        />
        <NumberInput
          placeholder="Min reward"
          min={0}
          value={minReward}
          onChange={(v) => setMinReward(v as number | "")}
        />
        <NumberInput
          placeholder="Max reward"
          min={0}
          value={maxReward}
          onChange={(v) => setMaxReward(v as number | "")}
        />
        <Select
          data={[
            { value: "deadline", label: "Deadline" },
            { value: "reward", label: "Reward" },
          ]}
          value={sortBy}
          onChange={(v) => setSortBy(v ?? "deadline")}
        />
        <Select
          data={[
            { value: "asc", label: "Asc" },
            { value: "desc", label: "Desc" },
          ]}
          value={sortOrder}
          onChange={(v) => setSortOrder(v ?? "asc")}
        />
      </Group>

      {error && (
        <Text c="red">{error}</Text>
      )}

      {loading && items.length === 0 ? (
        <Box style={{ display: "flex", justifyContent: "center", padding: "2rem" }}>
          <Loader />
        </Box>
      ) : (
        <SimpleGrid cols={{ base: 1, sm: 2, md: 3 }}>
          {items.map((order) => (
            <Card key={order.order_id} withBorder padding="md">
              <Text fw={600}>{order.name}</Text>
              <Text size="xs" c="dimmed">
                {supplierNames[order.supplier_id] ?? order.supplier_id}
              </Text>
              <Group justify="space-between">
                <Badge color="green">{order.reward} cr</Badge>
                <Text size="sm" c="dimmed">
                  {parseUtcDate(order.deadline).toLocaleString()}
                </Text>
              </Group>
              <Text size="sm">{order.pickup_location} → {order.delivery_location}</Text>
              <OrderStatusBadge status={order.status} />
              <Button fullWidth mt="sm" onClick={() => handleAccept(order.order_id)}>
                Accept
              </Button>
            </Card>
          ))}
        </SimpleGrid>
      )}
    </Stack>
  );
}
