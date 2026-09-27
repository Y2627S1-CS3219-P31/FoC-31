// AI-assisted (OpenCode + Claude): admin client account management. Lists
// users, supports search + status filter, suspend/reinstate, and creating a
// new administrator (role promotion). Live data via the gateway.
// Reviewed by authors.
import {
  Alert,
  Button,
  Card,
  Center,
  Group,
  Loader,
  Modal,
  Pagination,
  PasswordInput,
  Select,
  Stack,
  Table,
  Text,
  TextInput,
  Title,
} from "@mantine/core";
import { useDebouncedValue, useDisclosure } from "@mantine/hooks";
import { useForm } from "@mantine/form";
import { IconSearch, IconShieldPlus } from "@tabler/icons-react";
import { notifications } from "@mantine/notifications";
import { useCallback, useEffect, useState } from "react";
import { AccountStatusBadge } from "../../components/StatusPill";
import { ApiError, adminUsersApi } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import type { AdminUser } from "../../lib/types";

const PAGE_SIZE = 20;
type StatusFilter = "all" | "active" | "suspended";

export default function AdminClients() {
  const { user: current } = useAuth();

  const [q, setQ] = useState("");
  const [debouncedQ] = useDebouncedValue(q, 300);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [page, setPage] = useState(1);

  const [users, setUsers] = useState<AdminUser[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const [createOpen, createModal] = useDisclosure(false);
  const [creating, setCreating] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await adminUsersApi.list({
        limit: PAGE_SIZE,
        offset: (page - 1) * PAGE_SIZE,
        q: debouncedQ || undefined,
        status: statusFilter === "all" ? undefined : statusFilter,
      });
      setUsers(res.items);
      setTotal(res.total);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load users");
    } finally {
      setLoading(false);
    }
  }, [page, debouncedQ, statusFilter]);

  useEffect(() => {
    void load();
  }, [load]);

  // Reset to first page when the server-side search/filter changes.
  useEffect(() => {
    setPage(1);
  }, [debouncedQ, statusFilter]);

  const toggleSuspend = async (u: AdminUser) => {
    setBusyId(u.id);
    try {
      if (u.is_suspended) await adminUsersApi.unsuspend(u.id);
      else await adminUsersApi.suspend(u.id);
      notifications.show({
        color: "green",
        message: u.is_suspended ? "Account reinstated" : "Account suspended",
      });
      await load();
    } catch (err) {
      notifications.show({
        color: "red",
        message: err instanceof ApiError ? err.message : "Action failed",
      });
    } finally {
      setBusyId(null);
    }
  };

  const changeRole = async (u: AdminUser) => {
    const nextRole = u.role === "admin" ? "client" : "admin";
    setBusyId(u.id);
    try {
      await adminUsersApi.updateRole(u.id, nextRole);
      notifications.show({
        color: "green",
        message:
          nextRole === "admin"
            ? `${u.display_name} promoted to admin`
            : `${u.display_name} demoted to client`,
      });
      await load();
    } catch (err) {
      notifications.show({
        color: "red",
        message: err instanceof ApiError ? err.message : "Role change failed",
      });
    } finally {
      setBusyId(null);
    }
  };

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  const form = useForm({
    initialValues: {
      email: "",
      password: "",
      displayName: "",
      contactNumber: "",
    },
    validate: {
      email: (v) =>
        v.trim().toLowerCase().endsWith("@u.nus.edu")
          ? null
          : "Must be a @u.nus.edu address",
      password: (v) =>
        v.length >= 8 && /[A-Za-z]/.test(v) && /\d/.test(v)
          ? null
          : "At least 8 chars with letters and digits",
      displayName: (v) => (v.trim() ? null : "Display name required"),
      contactNumber: (v) =>
        v === "" || /^[89]\d{7}$/.test(v) ? null : "SG mobile: 8 digits",
    },
  });

  const handleCreateAdmin = form.onSubmit(async (values) => {
    setCreating(true);
    try {
      await adminUsersApi.createAdmin({
        email: values.email.trim().toLowerCase(),
        password: values.password,
        display_name: values.displayName.trim(),
        contact_number: values.contactNumber || null,
      });
      notifications.show({ color: "green", message: "Administrator created" });
      form.reset();
      createModal.close();
      await load();
    } catch (err) {
      notifications.show({
        color: "red",
        message: err instanceof ApiError ? err.message : "Create admin failed",
      });
    } finally {
      setCreating(false);
    }
  });

  return (
    <Stack gap="lg">
      <Group justify="space-between" align="flex-end" wrap="wrap">
        <div>
          <Title order={2}>Admin · Client Accounts</Title>
          <Text c="dimmed" size="sm">
            View status, suspend or reinstate accounts, and promote/demote roles
          </Text>
        </div>
        <Button leftSection={<IconShieldPlus size={16} />} onClick={createModal.open}>
          Create admin account
        </Button>
      </Group>

      <Group wrap="wrap">
        <TextInput
          leftSection={<IconSearch size={16} />}
          placeholder="Search by name or email..."
          value={q}
          onChange={(e) => setQ(e.currentTarget.value)}
          w={280}
        />
        <Select
          w={180}
          value={statusFilter}
          onChange={(v) => setStatusFilter((v as StatusFilter) ?? "all")}
          data={[
            { value: "all", label: "Status: All" },
            { value: "active", label: "Active" },
            { value: "suspended", label: "Suspended" },
          ]}
        />
      </Group>

      {error && (
        <Alert color="red" title="Error">
          {error}
        </Alert>
      )}

      <Card withBorder radius="md" p={0}>
        {loading ? (
          <Center h={160}>
            <Loader />
          </Center>
        ) : users.length === 0 ? (
          <Center h={140}>
            <Text c="dimmed">No accounts match your filters.</Text>
          </Center>
        ) : (
          <Table.ScrollContainer minWidth={640}>
            <Table highlightOnHover verticalSpacing="sm">
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>Name</Table.Th>
                  <Table.Th>Email</Table.Th>
                  <Table.Th>Role</Table.Th>
                  <Table.Th>Status</Table.Th>
                  <Table.Th>Actions</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {users.map((u) => {
                  const isSelf = current?.id === u.id;
                  const isAdmin = u.role === "admin";
                  return (
                    <Table.Tr key={u.id}>
                      <Table.Td fw={600}>{u.display_name}</Table.Td>
                      <Table.Td>{u.email}</Table.Td>
                      <Table.Td tt="capitalize">{u.role}</Table.Td>
                      <Table.Td>
                        <AccountStatusBadge suspended={u.is_suspended} />
                      </Table.Td>
                      <Table.Td>
                        {isSelf ? (
                          <Text size="sm" c="dimmed">
                            You
                          </Text>
                        ) : (
                          <Group gap="xs" wrap="nowrap">
                            {!isAdmin && (
                              <Button
                                size="xs"
                                variant="subtle"
                                color={u.is_suspended ? "green" : "red"}
                                loading={busyId === u.id}
                                onClick={() => toggleSuspend(u)}
                              >
                                {u.is_suspended ? "Reinstate" : "Suspend"}
                              </Button>
                            )}
                            <Button
                              size="xs"
                              variant="light"
                              color={isAdmin ? "gray" : "brand"}
                              loading={busyId === u.id}
                              onClick={() => changeRole(u)}
                            >
                              {isAdmin ? "Demote to client" : "Make admin"}
                            </Button>
                          </Group>
                        )}
                      </Table.Td>
                    </Table.Tr>
                  );
                })}
              </Table.Tbody>
            </Table>
          </Table.ScrollContainer>
        )}
      </Card>

      {totalPages > 1 && (
        <Group justify="center">
          <Pagination value={page} onChange={setPage} total={totalPages} />
        </Group>
      )}

      <Modal
        opened={createOpen}
        onClose={createModal.close}
        title="Create admin account"
        centered
      >
        <form onSubmit={handleCreateAdmin}>
          <Stack gap="sm">
            <Text size="sm" c="dimmed">
              Creates a brand-new account with the administrator role
              (pre-verified, ready to log in). To change an existing user's
              role instead, use “Make admin” / “Demote to client” in the table.
            </Text>
            <TextInput
              label="NUS Email"
              withAsterisk
              placeholder="e0123456@u.nus.edu"
              {...form.getInputProps("email")}
            />
            <TextInput
              label="Display name"
              withAsterisk
              {...form.getInputProps("displayName")}
            />
            <TextInput
              label="Contact number (optional)"
              placeholder="9XXXXXXX"
              {...form.getInputProps("contactNumber")}
            />
            <PasswordInput
              label="Temporary password"
              withAsterisk
              {...form.getInputProps("password")}
            />
            <Group justify="flex-end" mt="xs">
              <Button variant="default" onClick={createModal.close}>
                Cancel
              </Button>
              <Button type="submit" loading={creating}>
                Create admin
              </Button>
            </Group>
          </Stack>
        </form>
      </Modal>
    </Stack>
  );
}
