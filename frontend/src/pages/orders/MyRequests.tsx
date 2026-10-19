// AI-assisted: MyRequests page — requester's ongoing and completed orders with Edit/Delete/Cancel/Approve actions.
import {
  Box,
  Button,
  Group,
  Loader,
  Modal,
  NumberInput,
  Stack,
  Tabs,
  Text,
  Textarea,
  TextInput,
  Title,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useEffect, useState } from "react";
import { OrderStatusBadge } from "../../components/StatusPill";
import {
  ApiError,
  type OrderResponse,
  type OrderUpdate,
  ordersApi,
  parseUtcDate,
} from "../../lib/api";

const POLL_INTERVAL = 2000;
const POLL_TIMEOUT = 15000;

async function pollUntil<T>(
  fn: () => Promise<T>,
  done: (r: T) => boolean,
): Promise<T | "timeout"> {
  const deadline = Date.now() + POLL_TIMEOUT;
  while (Date.now() < deadline) {
    const r = await fn();
    if (done(r)) return r;
    await new Promise((res) => setTimeout(res, POLL_INTERVAL));
  }
  return "timeout";
}

interface EditForm {
  name: string;
  details: string;
  reward: number | "";
  deadline: string;
  pickupLocation: string;
  deliveryLocation: string;
}

export default function MyRequests() {
  const [activeTab, setActiveTab] = useState<string | null>("ongoing");

  const [ongoingItems, setOngoingItems] = useState<OrderResponse[]>([]);
  const [completedItems, setCompletedItems] = useState<OrderResponse[]>([]);
  const [loadingOngoing, setLoadingOngoing] = useState(true);
  const [loadingCompleted, setLoadingCompleted] = useState(false);
  const [errorOngoing, setErrorOngoing] = useState<string | null>(null);
  const [errorCompleted, setErrorCompleted] = useState<string | null>(null);

  const [pollingIds, setPollingIds] = useState<Set<string>>(new Set());

  const [editOrder, setEditOrder] = useState<OrderResponse | null>(null);
  const [editForm, setEditForm] = useState<EditForm>({
    name: "",
    details: "",
    reward: 1,
    deadline: "",
    pickupLocation: "",
    deliveryLocation: "",
  });
  const [editSubmitting, setEditSubmitting] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);

  const [cancelOrder, setCancelOrder] = useState<OrderResponse | null>(null);
  const [cancelReason, setCancelReason] = useState("");
  const [cancelSubmitting, setCancelSubmitting] = useState(false);
  const [cancelError, setCancelError] = useState<string | null>(null);

  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoadingOngoing(true);
    setErrorOngoing(null);
    ordersApi
      .requestedOngoing()
      .then((res) => {
        if (!cancelled) setOngoingItems(res);
      })
      .catch((err) => {
        if (!cancelled)
          setErrorOngoing(
            err instanceof ApiError ? err.message : "Failed to load",
          );
      })
      .finally(() => {
        if (!cancelled) setLoadingOngoing(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (activeTab !== "completed") return;
    let cancelled = false;
    setLoadingCompleted(true);
    setErrorCompleted(null);
    ordersApi
      .requestedCompleted()
      .then((res) => {
        if (!cancelled) setCompletedItems(res);
      })
      .catch((err) => {
        if (!cancelled)
          setErrorCompleted(
            err instanceof ApiError ? err.message : "Failed to load",
          );
      })
      .finally(() => {
        if (!cancelled) setLoadingCompleted(false);
      });
    return () => {
      cancelled = true;
    };
  }, [activeTab]);

  function addPolling(id: string) {
    setPollingIds((prev) => new Set(prev).add(id));
  }

  function removePolling(id: string) {
    setPollingIds((prev) => {
      const next = new Set(prev);
      next.delete(id);
      return next;
    });
  }

  function openEditModal(order: OrderResponse) {
    setEditError(null);
    const dt = parseUtcDate(order.deadline);
    const local = new Date(dt.getTime() - dt.getTimezoneOffset() * 60000)
      .toISOString()
      .slice(0, 16);
    setEditForm({
      name: order.name,
      details: order.details,
      reward: order.reward,
      deadline: local,
      pickupLocation: order.pickup_location,
      deliveryLocation: order.delivery_location,
    });
    setEditOrder(order);
  }

  async function handleEdit(e: React.FormEvent) {
    e.preventDefault();
    if (!editOrder) return;
    setEditError(null);
    const id = editOrder.order_id;
    const supplierId = editOrder.supplier_id;
    const body: OrderUpdate = {
      name: editForm.name,
      details: editForm.details,
      reward: editForm.reward as number,
      deadline: new Date(editForm.deadline).toISOString(),
      supplier_id: supplierId,
      pickup_location: editForm.pickupLocation,
      delivery_location: editForm.deliveryLocation,
    };
    setEditSubmitting(true);
    try {
      const actionResp = await ordersApi.update(id, body);
      setEditOrder(null);
      addPolling(id);
      const result = await pollUntil(
        () => ordersApi.pollUpdate(actionResp.task_id),
        (r) => r.status !== "pending",
      );
      if (result === "timeout") {
        notifications.show({
          color: "yellow",
          title: "Update",
          message: "Still processing",
        });
      } else if (result.status === "completed") {
        const updated = await ordersApi.requestedOngoing();
        setOngoingItems(updated);
        notifications.show({
          color: "green",
          title: "Updated",
          message: "Order updated",
        });
      } else {
        notifications.show({
          color: "red",
          title: "Update failed",
          message: result.failure_reason ?? "Unknown error",
        });
      }
    } catch (err) {
      setEditError(
        err instanceof ApiError ? err.message : "Failed to update",
      );
    } finally {
      removePolling(id);
      setEditSubmitting(false);
    }
  }

  async function handleDelete(id: string) {
    setDeleteConfirmId(null);
    addPolling(id);
    try {
      const actionResp = await ordersApi.delete(id);
      const result = await pollUntil(
        () => ordersApi.pollDeletion(actionResp.task_id),
        (r) => r.status !== "pending",
      );
      if (result === "timeout") {
        notifications.show({
          color: "yellow",
          title: "Delete",
          message: "Still processing",
        });
      } else if (result.status === "completed") {
        setOngoingItems((prev) => prev.filter((o) => o.order_id !== id));
        notifications.show({
          color: "green",
          title: "Deleted",
          message: "Order deleted",
        });
      } else {
        notifications.show({
          color: "red",
          title: "Delete failed",
          message: result.failure_reason ?? "Unknown error",
        });
      }
    } catch (err) {
      notifications.show({
        color: "red",
        title: "Delete failed",
        message: err instanceof ApiError ? err.message : "Failed to delete",
      });
    } finally {
      removePolling(id);
    }
  }

  function openCancelModal(order: OrderResponse) {
    setCancelReason("");
    setCancelError(null);
    setCancelOrder(order);
  }

  async function handleCancel(e: React.FormEvent) {
    e.preventDefault();
    if (!cancelOrder) return;
    setCancelError(null);
    const id = cancelOrder.order_id;
    const reason = cancelReason;
    setCancelSubmitting(true);
    try {
      await ordersApi.cancel(id, { reason });
      setCancelOrder(null);
      addPolling(id);
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
        setOngoingItems((prev) => prev.filter((o) => o.order_id !== id));
        window.dispatchEvent(new Event("credits-changed"));
        notifications.show({
          color: "green",
          title: "Cancelled",
          message: "Order cancelled",
        });
      }
    } catch (err) {
      setCancelError(
        err instanceof ApiError ? err.message : "Failed to cancel",
      );
    } finally {
      removePolling(id);
      setCancelSubmitting(false);
    }
  }

  async function handleApprove(id: string) {
    addPolling(id);
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
        const updated = await ordersApi.requestedOngoing();
        setOngoingItems(updated);
      } else {
        setOngoingItems((prev) => prev.filter((o) => o.order_id !== id));
        window.dispatchEvent(new Event("credits-changed"));
        notifications.show({
          color: "green",
          title: "Approved",
          message: "Order completed",
        });
      }
    } catch (err) {
      notifications.show({
        color: "red",
        title: "Approve failed",
        message: err instanceof ApiError ? err.message : "Failed to approve",
      });
    } finally {
      removePolling(id);
    }
  }

  function renderRow(order: OrderResponse) {
    const polling = pollingIds.has(order.order_id);
    const isOpen = order.status === "OPEN";
    const noAssign = order.courier_id === null;

    return (
      <Box
        key={order.order_id}
        p="sm"
        style={{ border: "1px solid #dee2e6", borderRadius: 8, marginBottom: 8 }}
      >
        <Group justify="space-between" wrap="nowrap" align="flex-start">
          <Stack gap={4}>
            <Text fw={600}>{order.name}</Text>
            <Group gap="xs" wrap="wrap">
              <OrderStatusBadge status={order.status} />
              <Text size="sm">Reward: {order.reward} cr</Text>
              <Text size="sm" c="dimmed">
                Deadline: {parseUtcDate(order.deadline).toLocaleString()}
              </Text>
              <Text size="sm" c="dimmed">
                Courier: {order.courier_id ? order.courier_id.slice(0, 8) + "…" : "Unassigned"}
              </Text>
            </Group>
          </Stack>
          <Group gap="xs" wrap="nowrap">
            {polling && <Loader size="sm" />}
            {!polling && isOpen && noAssign && (
              <>
                <Button
                  size="xs"
                  variant="outline"
                  onClick={() => openEditModal(order)}
                >
                  Edit
                </Button>
                {deleteConfirmId === order.order_id ? (
                  <Group gap="xs" wrap="nowrap">
                    <Text size="xs" c="red">
                      Confirm?
                    </Text>
                    <Button
                      size="xs"
                      color="red"
                      onClick={() => handleDelete(order.order_id)}
                    >
                      Yes
                    </Button>
                    <Button
                      size="xs"
                      variant="subtle"
                      onClick={() => setDeleteConfirmId(null)}
                    >
                      No
                    </Button>
                  </Group>
                ) : (
                  <Button
                    size="xs"
                    color="red"
                    variant="outline"
                    onClick={() => setDeleteConfirmId(order.order_id)}
                  >
                    Delete
                  </Button>
                )}
              </>
            )}
            {!polling && (isOpen || order.status === "ACCEPTED") && (
              <Button
                size="xs"
                color="orange"
                variant="outline"
                onClick={() => openCancelModal(order)}
              >
                Cancel
              </Button>
            )}
            {!polling && order.status === "AWAITING_APPROVAL" && (
              <Button
                size="xs"
                color="green"
                onClick={() => handleApprove(order.order_id)}
              >
                Approve
              </Button>
            )}
          </Group>
        </Group>
      </Box>
    );
  }

  return (
    <Stack gap="lg">
      <Title order={2}>My Requests</Title>

      <Tabs value={activeTab} onChange={setActiveTab}>
        <Tabs.List>
          <Tabs.Tab value="ongoing">Ongoing</Tabs.Tab>
          <Tabs.Tab value="completed">Completed</Tabs.Tab>
        </Tabs.List>

        <Tabs.Panel value="ongoing" pt="md">
          {loadingOngoing ? (
            <Box
              style={{
                display: "flex",
                justifyContent: "center",
                padding: "2rem",
              }}
            >
              <Loader />
            </Box>
          ) : errorOngoing ? (
            <Text c="red">{errorOngoing}</Text>
          ) : ongoingItems.length === 0 ? (
            <Text c="dimmed">No ongoing orders</Text>
          ) : (
            ongoingItems.map(renderRow)
          )}
        </Tabs.Panel>

        <Tabs.Panel value="completed" pt="md">
          {loadingCompleted ? (
            <Box
              style={{
                display: "flex",
                justifyContent: "center",
                padding: "2rem",
              }}
            >
              <Loader />
            </Box>
          ) : errorCompleted ? (
            <Text c="red">{errorCompleted}</Text>
          ) : completedItems.length === 0 ? (
            <Text c="dimmed">No completed orders</Text>
          ) : (
            completedItems.map(renderRow)
          )}
        </Tabs.Panel>
      </Tabs>

      <Modal
        opened={editOrder !== null}
        onClose={() => setEditOrder(null)}
        title="Edit Order"
        size="lg"
      >
        <form onSubmit={handleEdit}>
          <Stack gap="md">
            <TextInput
              label="Supplier (read-only)"
              value={editOrder?.supplier_id ?? ""}
              disabled
            />
            <TextInput
              label="Name"
              required
              value={editForm.name}
              onChange={(e) =>
                setEditForm((f) => ({ ...f, name: e.currentTarget.value }))
              }
            />
            <Textarea
              label="Details"
              required
              value={editForm.details}
              onChange={(e) =>
                setEditForm((f) => ({ ...f, details: e.currentTarget.value }))
              }
            />
            <NumberInput
              label="Reward (credits)"
              required
              min={1}
              value={editForm.reward}
              onChange={(v) =>
                setEditForm((f) => ({ ...f, reward: v as number | "" }))
              }
            />
            <TextInput
              label="Deadline"
              type="datetime-local"
              required
              value={editForm.deadline}
              onChange={(e) =>
                setEditForm((f) => ({ ...f, deadline: e.currentTarget.value }))
              }
            />
            <TextInput
              label="Pickup location"
              required
              value={editForm.pickupLocation}
              onChange={(e) =>
                setEditForm((f) => ({
                  ...f,
                  pickupLocation: e.currentTarget.value,
                }))
              }
            />
            <TextInput
              label="Delivery location"
              required
              value={editForm.deliveryLocation}
              onChange={(e) =>
                setEditForm((f) => ({
                  ...f,
                  deliveryLocation: e.currentTarget.value,
                }))
              }
            />
            {editError && (
              <Text c="red" size="sm">
                {editError}
              </Text>
            )}
            <Button type="submit" loading={editSubmitting}>
              Save
            </Button>
          </Stack>
        </form>
      </Modal>

      <Modal
        opened={cancelOrder !== null}
        onClose={() => setCancelOrder(null)}
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
            {cancelError && (
              <Text c="red" size="sm">
                {cancelError}
              </Text>
            )}
            <Button
              type="submit"
              color="red"
              loading={cancelSubmitting}
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
