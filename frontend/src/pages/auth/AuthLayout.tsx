// AI-assisted (OpenCode + Claude): centered auth card shell matching the
// Penpot login/verify wireframe. Reviewed by authors.
import { Box, Center, Group, Paper, Text } from "@mantine/core";
import { IconBuildingStore } from "@tabler/icons-react";
import type { ReactNode } from "react";

export function AuthLayout({ children }: { children: ReactNode }) {
  return (
    <Box mih="100vh" bg="gray.1">
      <Group justify="space-between" px="xl" py="md">
        <Group gap="xs">
          <IconBuildingStore size={22} />
          <Text fw={700}>Campus Errands</Text>
        </Group>
        <Text c="dimmed" size="sm" visibleFrom="xs">
          NUS peer-to-peer errand marketplace
        </Text>
      </Group>
      <Center px="md" pt={40}>
        <Paper withBorder shadow="sm" radius="md" p="xl" w={420} maw="100%">
          {children}
        </Paper>
      </Center>
    </Box>
  );
}
