// AI-assisted (OpenCode + Claude): profile view/edit. Role, email and account
// status are read-only (server rejects changes); only display name and contact
// number are editable. Reviewed by authors.
import {
  Badge,
  Button,
  Card,
  Group,
  Stack,
  Text,
  TextInput,
  Title,
} from "@mantine/core";
import { useForm } from "@mantine/form";
import { notifications } from "@mantine/notifications";
import { useEffect, useState } from "react";
import { ApiError, authApi } from "../lib/api";
import { useAuth } from "../lib/auth";

function ReadonlyField({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div>
      <Text size="xs" c="dimmed" tt="uppercase" fw={600}>
        {label}
      </Text>
      <Text>{value}</Text>
    </div>
  );
}

export default function Profile() {
  const { user, refresh } = useAuth();
  const [saving, setSaving] = useState(false);

  const form = useForm({
    initialValues: {
      displayName: user?.display_name ?? "",
      contactNumber: user?.contact_number ?? "",
    },
    validate: {
      displayName: (v) => (v.trim() ? null : "Display name required"),
      contactNumber: (v) =>
        v === "" || /^[89]\d{7}$/.test(v) ? null : "SG mobile: 8 digits",
    },
  });

  useEffect(() => {
    if (user) {
      form.setValues({
        displayName: user.display_name,
        contactNumber: user.contact_number ?? "",
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user]);

  const handleSubmit = form.onSubmit(async (values) => {
    setSaving(true);
    try {
      await authApi.updateMe({
        display_name: values.displayName.trim(),
        contact_number: values.contactNumber || null,
      });
      await refresh();
      notifications.show({ color: "green", message: "Profile updated" });
    } catch (err) {
      notifications.show({
        color: "red",
        message: err instanceof ApiError ? err.message : "Update failed",
      });
    } finally {
      setSaving(false);
    }
  });

  return (
    <Stack gap="lg" maw={560}>
      <div>
        <Title order={2}>Profile</Title>
        <Text c="dimmed" size="sm">
          Manage your account details
        </Text>
      </div>

      <Card withBorder radius="md" padding="lg">
        <Stack gap="md">
          <Group>
            <ReadonlyField label="Email" value={user?.email ?? "—"} />
            <ReadonlyField
              label="Role"
              value={
                <Badge
                  variant="light"
                  color={user?.role === "admin" ? "brand" : "gray"}
                  tt="capitalize"
                >
                  {user?.role ?? "—"}
                </Badge>
              }
            />
            <ReadonlyField
              label="Email verified"
              value={user?.email_verified ? "Yes" : "No"}
            />
          </Group>

          <form onSubmit={handleSubmit}>
            <Stack gap="sm">
              <TextInput
                label="Display name"
                withAsterisk
                {...form.getInputProps("displayName")}
              />
              <TextInput
                label="Contact number"
                placeholder="9XXXXXXX"
                {...form.getInputProps("contactNumber")}
              />
              <Group>
                <Button type="submit" loading={saving}>
                  Save changes
                </Button>
              </Group>
            </Stack>
          </form>
        </Stack>
      </Card>
    </Stack>
  );
}
