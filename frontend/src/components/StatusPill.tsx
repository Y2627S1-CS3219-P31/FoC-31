// AI-assisted: small status badge used across tables and order views.
import { Badge } from "@mantine/core";
import { OrderStatus } from "../lib/api";

export function ActiveBadge({ active }: { active: boolean }) {
  return (
    <Badge color={active ? "green" : "gray"} variant="light">
      {active ? "Active" : "Inactive"}
    </Badge>
  );
}

export function AccountStatusBadge({ suspended }: { suspended: boolean }) {
  return (
    <Badge color={suspended ? "red" : "green"} variant="light">
      {suspended ? "Suspended" : "Active"}
    </Badge>
  );
}

const ORDER_STATUS_COLORS: Record<OrderStatus, string> = {
  OPEN: "blue",
  ACCEPTED: "cyan",
  PICKED_UP: "yellow",
  AWAITING_APPROVAL: "orange",
  COMPLETED: "green",
  CANCELLED: "red",
  EXPIRED: "gray",
};

export function OrderStatusBadge({ status }: { status: OrderStatus }) {
  return (
    <Badge color={ORDER_STATUS_COLORS[status]} variant="light">
      {status}
    </Badge>
  );
}
