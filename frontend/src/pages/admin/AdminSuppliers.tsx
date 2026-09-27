// AI-assisted (OpenCode + Claude): admin supplier management. Table of
// suppliers on the left, create/edit form on the right, with deactivate
// confirmation. Live data via the gateway. Reviewed by authors.
import {
  ActionIcon,
  Alert,
  Button,
  Card,
  Center,
  Grid,
  Group,
  Loader,
  Modal,
  Pagination,
  Stack,
  Table,
  Text,
  TextInput,
  Title,
} from "@mantine/core";
import { useDebouncedValue, useDisclosure } from "@mantine/hooks";
import { notifications } from "@mantine/notifications";
import { IconEdit, IconPlus, IconSearch } from "@tabler/icons-react";
import { useCallback, useEffect, useState } from "react";
import { useLocation } from "react-router-dom";
import { ActiveBadge } from "../../components/StatusPill";
import { ApiError, suppliersApi } from "../../lib/api";
import type { Supplier, SupplierCreate } from "../../lib/types";
import { SupplierForm } from "./SupplierForm";

const PAGE_SIZE = 10;

export default function AdminSuppliers() {
  const location = useLocation();
  const editIdFromNav = (location.state as { editId?: string } | null)?.editId;

  const [q, setQ] = useState("");
  const [debouncedQ] = useDebouncedValue(q, 300);
  const [page, setPage] = useState(1);

  const [items, setItems] = useState<Supplier[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [editing, setEditing] = useState<Supplier | null>(null);
  const [creating, setCreating] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [confirmOpen, confirm] = useDisclosure(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await suppliersApi.list({
        q: debouncedQ || undefined,
        page,
        pageSize: PAGE_SIZE,
      });
      setItems(res.items);
      setTotal(res.total);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load suppliers");
    } finally {
      setLoading(false);
    }
  }, [debouncedQ, page]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    setPage(1);
  }, [debouncedQ]);

  // Deep link from the detail page "Edit / Manage" button.
  useEffect(() => {
    if (!editIdFromNav) return;
    suppliersApi
      .get(editIdFromNav)
      .then((s) => {
        setEditing(s);
        setCreating(false);
      })
      .catch(() => undefined);
  }, [editIdFromNav]);

  const notifyOk = (message: string) =>
    notifications.show({ color: "green", message });
  const notifyErr = (message: string) =>
    notifications.show({ color: "red", message });

  const handleSubmit = async (payload: SupplierCreate) => {
    setSubmitting(true);
    try {
      if (editing) {
        await suppliersApi.update(editing.id, payload);
        notifyOk("Supplier updated");
      } else {
        await suppliersApi.create(payload);
        notifyOk("Supplier created");
      }
      setEditing(null);
      setCreating(false);
      await load();
    } catch (err) {
      notifyErr(err instanceof ApiError ? err.message : "Save failed");
    } finally {
      setSubmitting(false);
    }
  };

  const handleDeactivate = async () => {
    if (!editing) return;
    setSubmitting(true);
    try {
      await suppliersApi.deactivate(editing.id);
      notifyOk("Supplier deactivated");
      confirm.close();
      setEditing(null);
      await load();
    } catch (err) {
      notifyErr(err instanceof ApiError ? err.message : "Deactivate failed");
    } finally {
      setSubmitting(false);
    }
  };

  const showForm = creating || editing !== null;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <Stack gap="lg">
      <div>
        <Title order={2}>Admin · Suppliers</Title>
        <Text c="dimmed" size="sm">
          Create, edit and deactivate campus suppliers
        </Text>
      </div>

      <Grid gutter="lg">
        <Grid.Col span={{ base: 12, md: showForm ? 7 : 12 }}>
          <Stack gap="sm">
            <Group justify="space-between" wrap="wrap">
              <TextInput
                leftSection={<IconSearch size={16} />}
                placeholder="Search suppliers..."
                value={q}
                onChange={(e) => setQ(e.currentTarget.value)}
                w={260}
              />
              <Button
                leftSection={<IconPlus size={16} />}
                onClick={() => {
                  setEditing(null);
                  setCreating(true);
                }}
              >
                New supplier
              </Button>
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
              ) : items.length === 0 ? (
                <Center h={140}>
                  <Text c="dimmed">No suppliers found.</Text>
                </Center>
              ) : (
                <Table.ScrollContainer minWidth={480}>
                  <Table highlightOnHover verticalSpacing="sm">
                    <Table.Thead>
                      <Table.Tr>
                        <Table.Th>Supplier</Table.Th>
                        <Table.Th>Category</Table.Th>
                        <Table.Th>Location</Table.Th>
                        <Table.Th>Status</Table.Th>
                        <Table.Th />
                      </Table.Tr>
                    </Table.Thead>
                    <Table.Tbody>
                      {items.map((s) => (
                        <Table.Tr key={s.id}>
                          <Table.Td fw={600}>{s.name}</Table.Td>
                          <Table.Td>{s.category}</Table.Td>
                          <Table.Td>{s.building}</Table.Td>
                          <Table.Td>
                            <ActiveBadge active={s.active} />
                          </Table.Td>
                          <Table.Td>
                            <ActionIcon
                              variant="subtle"
                              aria-label={`Edit ${s.name}`}
                              onClick={() => {
                                setCreating(false);
                                setEditing(s);
                              }}
                            >
                              <IconEdit size={18} />
                            </ActionIcon>
                          </Table.Td>
                        </Table.Tr>
                      ))}
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
          </Stack>
        </Grid.Col>

        {showForm && (
          <Grid.Col span={{ base: 12, md: 5 }}>
            <Card withBorder radius="md" padding="lg">
              <SupplierForm
                editing={editing}
                submitting={submitting}
                onSubmit={handleSubmit}
                onCancel={() => {
                  setEditing(null);
                  setCreating(false);
                }}
                onDeactivate={confirm.open}
              />
            </Card>
          </Grid.Col>
        )}
      </Grid>

      <Modal
        opened={confirmOpen}
        onClose={confirm.close}
        title="Deactivate supplier?"
        centered
      >
        <Stack>
          <Text>
            This will hide <b>{editing?.name}</b> from active listings. You can
            reactivate it later by editing the record.
          </Text>
          <Group justify="flex-end">
            <Button variant="default" onClick={confirm.close}>
              Cancel
            </Button>
            <Button color="red" loading={submitting} onClick={handleDeactivate}>
              Deactivate
            </Button>
          </Group>
        </Stack>
      </Modal>
    </Stack>
  );
}
