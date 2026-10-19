// AI-assisted: OrderDetail page — view all fields for a single order with role-based actions.
import {
  Badge,
  Box,
  Button,
  Group,
  Loader,
  Modal,
  Stack,
  Text,
  Textarea,
  Title,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { useAuth } from "../../lib/auth";
import { ApiError, type OrderResponse, type OrderStatus, ordersApi, parseUtcDate } from "../../lib/api";

const POLL_INTERVAL = 2000;
const POLL_TIMEOUT = 15000;

async function pollUntil(
  fn: () => Promise<OrderResponse>,
  done: (r: OrderResponse) => boolean,
): Promise<OrderResponse | "timeout"> {
  const deadline = Date.now() + POLL_TIMEOUT;
  while (Date.now() < deadline) {
    const r = await fn();
    if (done(r)) return r;
    await new Promise((res) => setTimeout(res, POLL_INTERVAL));
  }
  return "timeout";
}

const TIMELINE_STATUSES: OrderStatus[] = [
  "OPEN",
  "ACCEPTED",
  "PICKED_UP",
  "AWAITING_APPROVAL",
  "COMPLETED",
];

function StatusTimeline({ status }: { status: OrderStatus }) {
  const isTerminal = status === "CANCELLED" || status === "EXPIRED";
  const steps = isTerminal
    ? (TIMELINE_STATUSES.slice(0, -1) as OrderStatus[]).concat([status])
    : TIMELINE_STATUSES;

  return (
    <Group gap="xs" wrap="wrap" align="center">
      {steps.map((s, i) => {
        const isCurrent = s === status;
        const isPast =
          !isTerminal && TIMELINE_STATUSES.indexOf(s) < TIMELINE_STATUSES.indexOf(status);
        return (
          <Group key={s} gap={4} wrap="nowrap" align="center">
            <Badge
              variant={isCurrent ? "filled" : isPast ? "light" : "outline"}
              color={
                isCurrent
                  ? s === "CANCELLED" || s === "EXPIRED"
                    ? "red"
                    : s === "COMPLETED"
                    ? "green"
                    : "blue"
                  : "gray"
              }
              size="sm"
            >
              {s}
            </Badge>
            {i < steps.length - 1 && (
              <Text size="xs" c="dimmed">
                →
              </Text>
            )}
          </Group>
        );
      })}
    </Group>
  );
}

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <Group gap="sm" align="flex-start">
      <Text size="sm" fw={600} style={{ minWidth: 140 }}>
        {label}
      </Text>
      <Text size="sm">{value}</Text>
    </Group>
  );
}

export default function OrderDetail() {
  const { id } = useParams<{ id: string }>();
  const { user } = useAuth();

  const [order, setOrder] = useState<OrderResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);

  const [cancelModalOpen, setCancelModalOpen] = useState(false);
  const [cancelReason, setCancelReason] = useState("");
  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    setLoading(true);
    ordersApi
      .get(id)
      .then((res) => {
        if (!cancelled) setOrder(res);
      })
      .catch((err) => {
        if (!cancelled)
          notifications.show({
            color: "red",
            title: "Failed to load order",
            message: err instanceof ApiError ? err.message : "Failed to load",
          });
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [id]);

  async function refreshOrder() {
    if (!id) return;
    try {
      const updated = await ordersApi.get(id);
      setOrder(updated);
    } catch (err) {
      notifications.show({
        color: "red",
        title: "Failed to refresh",
        message: err instanceof ApiError ? err.message : "Failed to refresh",
      });
    }
  }

  async function handleAccept() {
    if (!id) return;
    setActionLoading(true);
    try {
      await ordersApi.accept(id);
      await refreshOrder();
    } catch (err) {
      notifications.show({
        color: "red",
        title: "Accept failed",
        message: err instanceof ApiError ? err.message : "Failed to accept",
      });
    } finally {
      setActionLoading(false);
    }
  }

  async function handleWithdraw() {
    if (!id) return;
    setActionLoading(true);
    try {
      await ordersApi.withdraw(id);
      await refreshOrder();
    } catch (err) {
      notifications.show({
        color: "red",
        title: "Withdraw failed",
        message: err instanceof ApiError ? err.message : "Failed to withdraw",
      });
    } finally {
      setActionLoading(false);
    }
  }

  async function handlePickup() {
    if (!id) return;
    setActionLoading(true);
    try {
      await ordersApi.pickup(id);
      await refreshOrder();
    } catch (err) {
      notifications.show({
        color: "red",
        title: "Pick up failed",
        message: err instanceof ApiError ? err.message : "Failed to pick up",
      });
    } finally {
      setActionLoading(false);
    }
  }

  async function handleDeliver() {
    if (!id) return;
    setActionLoading(true);
    try {
      await ordersApi.deliver(id);
      await refreshOrder();
    } catch (err) {
      notifications.show({
        color: "red",
        title: "Deliver failed",
        message: err instanceof ApiError ? err.message : "Failed to deliver",
      });
    } finally {
      setActionLoading(false);
    }
  }

  function openCancelModal() {
    setCancelReason("");
    setCancelModalOpen(true);
  }

  async function handleCancel(e: React.FormEvent) {
    e.preventDefault();
    if (!id) return;
    setActionLoading(true);
    setCancelModalOpen(false);
    try {
      await ordersApi.cancel(id, { reason: cancelReason });
      const result = await pollUntil(
        () => ordersApi.get(id),
        (r) => r.status === "CANCELLED",
      );
      if (result === "timeout") {
        notifications.show({
          color: "yellow",
          title: "Cancel",
          message: "Still processing",
        });
      } else {
        window.dispatchEvent(new Event("credits-changed"));
        notifications.show({
          color: "green",
          title: "Cancelled",
          message: "Order cancelled",
        });
      }
      await refreshOrder();
    } catch (err) {
      notifications.show({
        color: "red",
        title: "Cancel failed",
        message: err instanceof ApiError ? err.message : "Failed to cancel",
      });
    } finally {
      setActionLoading(false);
    }
  }

  async function handleApprove() {
    if (!id) return;
    setActionLoading(true);
    try {
      await ordersApi.approve(id);
      const result = await pollUntil(
        () => ordersApi.get(id),
        (r) => r.status === "COMPLETED",
      );
      if (result === "timeout") {
        notifications.show({
          color: "yellow",
          title: "Approve",
          message: "Still processing",
        });
      } else {
        window.dispatchEvent(new Event("credits-changed"));
        notifications.show({
          color: "green",
          title: "Approved",
          message: "Order completed",
        });
      }
      await refreshOrder();
    } catch (err) {
      notifications.show({
        color: "red",
        title: "Approve failed",
        message: err instanceof ApiError ? err.message : "Failed to approve",
      });
    } finally {
      setActionLoading(false);
    }
  }

  if (loading) {
    return (
      <Box style={{ display: "flex", justifyContent: "center", padding: "2rem" }}>
        <Loader />
      </Box>
    );
  }

  if (!order) {
    return <Text c="dimmed">Order not found.</Text>;
  }

  const userId = user?.id ?? "";
  const isRequester = userId === order.requester_id;
  const isCourier = userId === order.courier_id;
  const isNeither = !isRequester && !isCourier;

  return (
    <Stack gap="lg">
      <Title order={2}>{order.name}</Title>

      <Box p="md" style={{ border: "1px solid #dee2e6", borderRadius: 8 }}>
        <Stack gap="xs">
          <DetailRow label="Order ID" value={order.order_id} />
          <DetailRow label="Details" value={order.details} />
          <DetailRow label="Reward" value={`${order.reward} credits`} />
          <DetailRow label="Deadline" value={parseUtcDate(order.deadline).toLocaleString()} />
          <DetailRow label="Pickup" value={order.pickup_location} />
          <DetailRow label="Delivery" value={order.delivery_location} />
          <DetailRow label="Supplier" value={order.supplier_id} />
          <DetailRow label="Requester" value={order.requester_id} />
          <DetailRow label="Courier" value={order.courier_id ?? "Unassigned"} />
          <DetailRow label="Created" value={parseUtcDate(order.created_at).toLocaleString()} />
        </Stack>
      </Box>

      <Box>
        <Text fw={600} mb="xs">
          Status
        </Text>
        <StatusTimeline status={order.status} />
      </Box>

      <Group gap="xs">
        {actionLoading && <Loader size="sm" />}

        {!actionLoading && isNeither && order.status === "OPEN" && (
          <Button onClick={handleAccept}>Accept</Button>
        )}

        {!actionLoading && isRequester && (order.status === "OPEN" || order.status === "ACCEPTED") && (
          <Button color="orange" variant="outline" onClick={openCancelModal}>
            Cancel
          </Button>
        )}

        {!actionLoading && isRequester && order.status === "AWAITING_APPROVAL" && (
          <Button color="green" onClick={handleApprove}>
            Approve
          </Button>
        )}

        {!actionLoading && isCourier && order.status === "ACCEPTED" && (
          <>
            <Button onClick={handlePickup}>Pick up</Button>
            <Button color="red" variant="outline" onClick={handleWithdraw}>
              Withdraw
            </Button>
          </>
        )}

        {!actionLoading && isCourier && order.status === "PICKED_UP" && (
          <Button color="green" onClick={handleDeliver}>
            Mark delivered
          </Button>
        )}
      </Group>

      <Modal
        opened={cancelModalOpen}
        onClose={() => setCancelModalOpen(false)}
        title="Cancel Order"
      >
        <form onSubmit={handleCancel}>
          <Stack gap="md">
            <Textarea
              label="Reason"
              required
              value={cancelReason}
              onChange={(e) => setCancelReason(e.currentTarget.value)}
            />
            <Button
              type="submit"
              color="red"
              disabled={!cancelReason.trim()}
            >
              Confirm Cancel
            </Button>
          </Stack>
        </form>
      </Modal>
    </Stack>
  );
}
