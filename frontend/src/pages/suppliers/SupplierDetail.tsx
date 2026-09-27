// AI-assisted (OpenCode + Claude): supplier detail view. Admins get edit /
// deactivate actions. Reviewed by authors.
import {
  Alert,
  Anchor,
  Badge,
  Button,
  Card,
  Center,
  Group,
  Image,
  Loader,
  Stack,
  Text,
  Title,
} from "@mantine/core";
import { IconArrowLeft, IconEdit } from "@tabler/icons-react";
import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ActiveBadge } from "../../components/StatusPill";
import { ApiError, suppliersApi } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import type { Supplier } from "../../lib/types";

function Field({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div>
      <Text size="xs" c="dimmed" tt="uppercase" fw={600}>
        {label}
      </Text>
      <Text>{value ?? "—"}</Text>
    </div>
  );
}

export default function SupplierDetail() {
  const { id } = useParams<{ id: string }>();
  const { isAdmin } = useAuth();
  const navigate = useNavigate();

  const [supplier, setSupplier] = useState<Supplier | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    setLoading(true);
    suppliersApi
      .get(id)
      .then((s) => !cancelled && setSupplier(s))
      .catch(
        (err) =>
          !cancelled &&
          setError(err instanceof ApiError ? err.message : "Failed to load"),
      )
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [id]);

  if (loading) {
    return (
      <Center h={200}>
        <Loader />
      </Center>
    );
  }

  if (error || !supplier) {
    return (
      <Stack>
        <Anchor component={Link} to="/suppliers">
          <Group gap={4}>
            <IconArrowLeft size={16} /> Back to suppliers
          </Group>
        </Anchor>
        <Alert color="red" title="Error">
          {error ?? "Supplier not found"}
        </Alert>
      </Stack>
    );
  }

  const hours =
    supplier.startingTime && supplier.closingTime
      ? `${supplier.startingTime} – ${supplier.closingTime}`
      : null;
  const coords =
    supplier.latitude != null && supplier.longitude != null
      ? `${supplier.latitude}, ${supplier.longitude}`
      : null;

  return (
    <Stack gap="lg">
      <Anchor component={Link} to="/suppliers">
        <Group gap={4}>
          <IconArrowLeft size={16} /> Back to suppliers
        </Group>
      </Anchor>

      <Card withBorder radius="md" padding="lg">
        <Stack gap="md">
          {supplier.imageUrl ? (
            <Image
              src={supplier.imageUrl}
              h={220}
              radius="sm"
              fit="cover"
              alt={supplier.name}
            />
          ) : null}

          <Group justify="space-between" align="flex-start" wrap="wrap">
            <div>
              <Title order={2}>{supplier.name}</Title>
              <Group gap="xs" mt={4}>
                <Badge variant="light" color="brand">
                  {supplier.category}
                </Badge>
                <ActiveBadge active={supplier.active} />
              </Group>
            </div>
            {isAdmin && (
              <Button
                variant="light"
                leftSection={<IconEdit size={16} />}
                onClick={() =>
                  navigate("/admin/suppliers", { state: { editId: supplier.id } })
                }
              >
                Edit / Manage
              </Button>
            )}
          </Group>

          <Stack gap="sm">
            <Field label="Building" value={supplier.building} />
            <Field label="Floor" value={supplier.floor} />
            <Field label="Location" value={supplier.locationDescription} />
            <Field label="Opening hours" value={hours} />
            <Field label="Coordinates" value={coords} />
          </Stack>
        </Stack>
      </Card>
    </Stack>
  );
}
