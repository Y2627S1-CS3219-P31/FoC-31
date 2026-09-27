// AI-assisted (OpenCode + Claude): supplier summary card used in the browse
// grid. Reviewed by authors.
import { Badge, Card, Group, Image, Stack, Text } from "@mantine/core";
import { IconClock, IconMapPin } from "@tabler/icons-react";
import { Link } from "react-router-dom";
import type { Supplier } from "../lib/types";
import { ActiveBadge } from "./StatusPill";

export function SupplierCard({ supplier }: { supplier: Supplier }) {
  const hours =
    supplier.startingTime && supplier.closingTime
      ? `${supplier.startingTime} – ${supplier.closingTime}`
      : null;

  return (
    <Card
      withBorder
      radius="md"
      padding="md"
      component={Link}
      to={`/suppliers/${supplier.id}`}
      style={{ textDecoration: "none", color: "inherit", height: "100%" }}
    >
      <Stack gap="xs" h="100%">
        {supplier.imageUrl ? (
          <Image
            src={supplier.imageUrl}
            h={120}
            radius="sm"
            fit="cover"
            alt={supplier.name}
          />
        ) : null}
        <Group justify="space-between" wrap="nowrap" align="flex-start">
          <Text fw={700} lineClamp={2}>
            {supplier.name}
          </Text>
          <ActiveBadge active={supplier.active} />
        </Group>
        <Badge variant="light" color="brand" w="fit-content">
          {supplier.category}
        </Badge>
        <Group gap={6} c="dimmed">
          <IconMapPin size={16} />
          <Text size="sm" lineClamp={1}>
            {supplier.building}
            {supplier.floor ? `, ${supplier.floor}` : ""}
          </Text>
        </Group>
        {hours ? (
          <Group gap={6} c="dimmed">
            <IconClock size={16} />
            <Text size="sm">{hours}</Text>
          </Group>
        ) : null}
      </Stack>
    </Card>
  );
}
