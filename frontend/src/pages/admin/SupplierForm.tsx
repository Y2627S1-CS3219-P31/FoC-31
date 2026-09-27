// AI-assisted (OpenCode + Claude): create/edit supplier form used in the admin
// suppliers screen. Validates to the supplier-service constraints.
// Reviewed by authors.
import {
  Button,
  Group,
  NumberInput,
  Select,
  Stack,
  Text,
  TextInput,
  Title,
} from "@mantine/core";
import { useForm } from "@mantine/form";
import { useEffect } from "react";
import {
  SUPPLIER_CATEGORIES,
  type Category,
  type Supplier,
  type SupplierCreate,
} from "../../lib/types";

const TIME_RE = /^([01]\d|2[0-3]):[0-5]\d$/;

export interface SupplierFormValues {
  name: string;
  category: Category | null;
  building: string;
  floor: string;
  locationDescription: string;
  latitude: number | "";
  longitude: number | "";
  startingTime: string;
  closingTime: string;
  imageUrl: string;
}

function toFormValues(s: Supplier | null): SupplierFormValues {
  return {
    name: s?.name ?? "",
    category: s?.category ?? null,
    building: s?.building ?? "",
    floor: s?.floor ?? "",
    locationDescription: s?.locationDescription ?? "",
    latitude: s?.latitude ?? "",
    longitude: s?.longitude ?? "",
    startingTime: s?.startingTime ?? "",
    closingTime: s?.closingTime ?? "",
    imageUrl: s?.imageUrl ?? "",
  };
}

export function buildPayload(v: SupplierFormValues): SupplierCreate {
  return {
    name: v.name.trim(),
    category: v.category as Category,
    building: v.building.trim(),
    floor: v.floor.trim() || null,
    locationDescription: v.locationDescription.trim() || null,
    latitude: v.latitude === "" ? null : Number(v.latitude),
    longitude: v.longitude === "" ? null : Number(v.longitude),
    startingTime: v.startingTime.trim() || null,
    closingTime: v.closingTime.trim() || null,
    imageUrl: v.imageUrl.trim() || null,
  };
}

interface Props {
  editing: Supplier | null;
  submitting: boolean;
  onSubmit: (payload: SupplierCreate) => void;
  onCancel: () => void;
  onDeactivate?: () => void;
  onReactivate?: () => void;
}

export function SupplierForm({
  editing,
  submitting,
  onSubmit,
  onCancel,
  onDeactivate,
  onReactivate,
}: Props) {
  const form = useForm<SupplierFormValues>({
    initialValues: toFormValues(editing),
    validate: {
      name: (v) => (v.trim() ? null : "Name is required"),
      category: (v) => (v ? null : "Category is required"),
      building: (v) => (v.trim() ? null : "Campus location is required"),
      startingTime: (v) =>
        !v || TIME_RE.test(v) ? null : "Use HH:MM (24h)",
      closingTime: (v) => (!v || TIME_RE.test(v) ? null : "Use HH:MM (24h)"),
    },
  });

  useEffect(() => {
    form.setValues(toFormValues(editing));
    form.resetDirty(toFormValues(editing));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editing]);

  return (
    <form onSubmit={form.onSubmit((v) => onSubmit(buildPayload(v)))}>
      <Stack gap="sm">
        <Title order={4}>{editing ? "Edit supplier" : "New supplier"}</Title>

        <TextInput
          label="Name"
          withAsterisk
          placeholder="CoffeeBean @ COM3"
          {...form.getInputProps("name")}
        />
        <Select
          label="Category"
          withAsterisk
          data={SUPPLIER_CATEGORIES.map((c) => ({ value: c, label: c }))}
          {...form.getInputProps("category")}
        />
        <TextInput
          label="Campus location (building)"
          withAsterisk
          placeholder="COM3"
          {...form.getInputProps("building")}
        />
        <TextInput
          label="Floor"
          placeholder="Level 1"
          {...form.getInputProps("floor")}
        />
        <TextInput
          label="Location description"
          placeholder="Near the entrance"
          {...form.getInputProps("locationDescription")}
        />
        <Group grow>
          <TextInput
            label="Opening time"
            placeholder="08:00"
            {...form.getInputProps("startingTime")}
          />
          <TextInput
            label="Closing time"
            placeholder="20:00"
            {...form.getInputProps("closingTime")}
          />
        </Group>
        <Group grow>
          <NumberInput
            label="Latitude"
            min={-90}
            max={90}
            decimalScale={6}
            {...form.getInputProps("latitude")}
          />
          <NumberInput
            label="Longitude"
            min={-180}
            max={180}
            decimalScale={6}
            {...form.getInputProps("longitude")}
          />
        </Group>
        <TextInput
          label="Image URL"
          placeholder="https://..."
          {...form.getInputProps("imageUrl")}
        />

        <Group justify="space-between" mt="xs">
          <Group gap="xs">
            <Button type="submit" loading={submitting}>
              {editing ? "Save" : "Create"}
            </Button>
            <Button variant="subtle" color="gray" onClick={onCancel}>
              Cancel
            </Button>
          </Group>
          {editing && editing.active && onDeactivate && (
            <Button variant="subtle" color="red" onClick={onDeactivate}>
              Deactivate
            </Button>
          )}
          {editing && !editing.active && onReactivate && (
            <Button variant="subtle" color="green" onClick={onReactivate}>
              Reactivate
            </Button>
          )}
        </Group>
        {editing && !editing.active && (
          <Text size="sm" c="dimmed">
            This supplier is currently inactive.
          </Text>
        )}
      </Stack>
    </form>
  );
}
