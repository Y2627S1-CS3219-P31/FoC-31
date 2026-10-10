// AI-assisted (OpenCode + Claude): small status badge used across tables.
// Reviewed by authors.
import { Badge } from "@mantine/core";

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
