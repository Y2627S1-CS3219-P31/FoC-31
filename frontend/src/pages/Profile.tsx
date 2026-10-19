// AI-assisted (OpenCode + Claude): profile view/edit and credits balance/history.
// Role, email and account status are read-only (server rejects changes); only
// display name and contact number are editable. Reviewed by authors.
import {
  Badge,
  Button,
  Card,
  Group,
  Loader,
  Stack,
  Table,
  Text,
  TextInput,
  Title,
} from "@mantine/core";
import { useForm } from "@mantine/form";
import { notifications } from "@mantine/notifications";
import { useEffect, useState } from "react";
import {
  ApiError,
  BalanceResponse,
  TransactionResponse,
  authApi,
  creditsApi,
} from "../lib/api";
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
  const [balance, setBalance] = useState<BalanceResponse | null>(null);
  const [transactions, setTransactions] = useState<TransactionResponse[]>([]);
  const [creditsLoading, setCreditsLoading] = useState(true);

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

  useEffect(() => {
    if (!user) return;
    let cancelled = false;
    setCreditsLoading(true);
    Promise.all([
      creditsApi.getBalance(user.id),
      creditsApi.getTransactions(user.id),
    ])
      .then(([bal, txns]) => {
        if (cancelled) return;
        setBalance(bal);
        setTransactions(txns);
      })
      .catch((err) => {
        if (cancelled) return;
        notifications.show({
          color: "red",
          message: err instanceof ApiError ? err.message : "Failed to load credits",
        });
      })
      .finally(() => {
        if (!cancelled) setCreditsLoading(false);
      });
    return () => { cancelled = true; };
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

      <Card withBorder radius="md" padding="lg">
        <Stack gap="md">
          <Title order={4}>Credits</Title>
          {creditsLoading ? (
            <Loader size="sm" />
          ) : (
            <>
              <Group>
                <div>
                  <Text size="xs" c="dimmed" tt="uppercase" fw={600}>Available</Text>
                  <Text fw={600}>{balance?.available_balance ?? "—"}</Text>
                </div>
                <div>
                  <Text size="xs" c="dimmed" tt="uppercase" fw={600}>Reserved</Text>
                  <Text>{balance?.reserved_balance ?? "—"}</Text>
                </div>
              </Group>
              <Table striped highlightOnHover withTableBorder>
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th>Kind</Table.Th>
                    <Table.Th>Amount</Table.Th>
                    <Table.Th>Order ID</Table.Th>
                    <Table.Th>Time</Table.Th>
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {transactions.length === 0 ? (
                    <Table.Tr>
                      <Table.Td colSpan={4}>
                        <Text c="dimmed" size="sm" ta="center">No transactions yet</Text>
                      </Table.Td>
                    </Table.Tr>
                  ) : (
                    transactions.map((tx) => (
                      <Table.Tr key={tx.id}>
                        <Table.Td>{tx.kind}</Table.Td>
                        <Table.Td>
                          <Text c={tx.amount >= 0 ? "green" : "red"}>
                            {tx.amount >= 0 ? "+" : ""}{tx.amount}
                          </Text>
                        </Table.Td>
                        <Table.Td>{tx.order_id ?? "—"}</Table.Td>
                        <Table.Td>{new Date(tx.created_at).toLocaleString()}</Table.Td>
                      </Table.Tr>
                    ))
                  )}
                </Table.Tbody>
              </Table>
            </>
          )}
        </Stack>
      </Card>
    </Stack>
  );
}
