// AI-assisted (OpenCode + Claude): responsive app shell with a desktop navbar
// and a mobile bottom tab bar, matching the team's Penpot wireframe.
// Reviewed by authors.
import {
  ActionIcon,
  AppShell,
  Avatar,
  Badge,
  Box,
  Burger,
  Drawer,
  Group,
  NavLink as MantineNavLink,
  Stack,
  Text,
} from "@mantine/core";
import { useDisclosure } from "@mantine/hooks";
import {
  IconBuildingStore,
  IconLogout,
  IconShieldCog,
  IconUser,
  IconUsers,
} from "@tabler/icons-react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "../lib/auth";

interface NavItem {
  to: string;
  label: string;
  icon: React.ReactNode;
  adminOnly?: boolean;
}

const NAV_ITEMS: NavItem[] = [
  { to: "/suppliers", label: "Suppliers", icon: <IconBuildingStore size={18} /> },
  { to: "/profile", label: "Profile", icon: <IconUser size={18} /> },
  {
    to: "/admin/suppliers",
    label: "Manage Suppliers",
    icon: <IconShieldCog size={18} />,
    adminOnly: true,
  },
  {
    to: "/admin/clients",
    label: "Client Accounts",
    icon: <IconUsers size={18} />,
    adminOnly: true,
  },
];

function initials(name: string | undefined, email: string | undefined): string {
  if (name) {
    const parts = name.trim().split(/\s+/);
    return (parts[0]?.[0] ?? "") + (parts[1]?.[0] ?? "");
  }
  return (email?.[0] ?? "?").toUpperCase();
}

export function AppLayout() {
  const { user, role, isAdmin, logout } = useAuth();
  const navigate = useNavigate();
  const [drawerOpened, drawer] = useDisclosure(false);

  const items = NAV_ITEMS.filter((i) => !i.adminOnly || isAdmin);

  const handleLogout = () => {
    logout();
    navigate("/login", { replace: true });
  };

  return (
    <AppShell header={{ height: 60 }} padding="md">
      <AppShell.Header>
        <Group h="100%" px="md" justify="space-between" wrap="nowrap">
          <Group gap="xs" wrap="nowrap">
            <IconBuildingStore size={22} />
            <Text fw={700} size="lg">
              Campus Errands
            </Text>
          </Group>

          {/* Desktop nav */}
          <Group gap="lg" visibleFrom="sm" wrap="nowrap">
            {items.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                style={({ isActive }) => ({
                  textDecoration: "none",
                  fontWeight: 600,
                  color: isActive ? "var(--mantine-color-brand-7)" : "#495057",
                  borderBottom: isActive
                    ? "2px solid var(--mantine-color-brand-6)"
                    : "2px solid transparent",
                  paddingBottom: 4,
                })}
              >
                {item.label}
              </NavLink>
            ))}
          </Group>

          <Group gap="sm" wrap="nowrap">
            {role && (
              <Badge
                color={isAdmin ? "brand" : "gray"}
                variant="light"
                visibleFrom="xs"
              >
                {isAdmin ? "Admin" : "Client"}
              </Badge>
            )}
            <Avatar radius="xl" color="brand" size="sm" visibleFrom="sm">
              {initials(user?.display_name, user?.email)}
            </Avatar>
            <ActionIcon
              variant="subtle"
              color="gray"
              onClick={handleLogout}
              visibleFrom="sm"
              aria-label="Log out"
            >
              <IconLogout size={20} />
            </ActionIcon>
            {/* Mobile burger */}
            <Burger
              opened={drawerOpened}
              onClick={drawer.toggle}
              hiddenFrom="sm"
              size="sm"
            />
          </Group>
        </Group>
      </AppShell.Header>

      <AppShell.Main>
        <Box maw={1080} mx="auto">
          <Outlet />
        </Box>
      </AppShell.Main>

      {/* Mobile navigation drawer */}
      <Drawer
        opened={drawerOpened}
        onClose={drawer.close}
        title="Menu"
        hiddenFrom="sm"
        size="70%"
      >
        <Stack gap="xs">
          {role && (
            <Badge color={isAdmin ? "brand" : "gray"} variant="light">
              {isAdmin ? "Admin" : "Client"}
            </Badge>
          )}
          {items.map((item) => (
            <MantineNavLink
              key={item.to}
              component={NavLink}
              to={item.to}
              label={item.label}
              leftSection={item.icon}
              onClick={drawer.close}
            />
          ))}
          <MantineNavLink
            label="Log out"
            leftSection={<IconLogout size={18} />}
            onClick={() => {
              drawer.close();
              handleLogout();
            }}
          />
        </Stack>
      </Drawer>
    </AppShell>
  );
}
