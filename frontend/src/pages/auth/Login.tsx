// AI-assisted (OpenCode + Claude): login screen. Reviewed by authors.
import {
  Anchor,
  Button,
  PasswordInput,
  Stack,
  Tabs,
  Text,
  TextInput,
  Title,
} from "@mantine/core";
import { useForm } from "@mantine/form";
import { notifications } from "@mantine/notifications";
import { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { ApiError } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { AuthLayout } from "./AuthLayout";

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [submitting, setSubmitting] = useState(false);

  const form = useForm({
    initialValues: { email: "", password: "" },
    validate: {
      email: (v) => (/^\S+@\S+$/.test(v) ? null : "Enter a valid email"),
      password: (v) => (v.length > 0 ? null : "Password is required"),
    },
  });

  const from =
    (location.state as { from?: string } | null)?.from ?? "/suppliers";

  const handleSubmit = form.onSubmit(async (values) => {
    setSubmitting(true);
    try {
      const profile = await login(values.email.trim(), values.password);
      notifications.show({
        color: "green",
        message: `Welcome back, ${profile.display_name}`,
      });
      navigate(from, { replace: true });
    } catch (err) {
      const message =
        err instanceof ApiError ? err.message : "Login failed. Try again.";
      notifications.show({ color: "red", message });
    } finally {
      setSubmitting(false);
    }
  });

  return (
    <AuthLayout>
      <Stack gap="md">
        <div>
          <Title order={3}>Welcome back</Title>
          <Text c="dimmed" size="sm">
            Log in with your NUS account to continue
          </Text>
        </div>

        <Tabs
          value="login"
          onChange={(v) => v === "signup" && navigate("/register")}
        >
          <Tabs.List grow>
            <Tabs.Tab value="login">Log In</Tabs.Tab>
            <Tabs.Tab value="signup">Sign Up</Tabs.Tab>
          </Tabs.List>
        </Tabs>

        <form onSubmit={handleSubmit}>
          <Stack gap="sm">
            <TextInput
              label="NUS Email"
              placeholder="e0123456@u.nus.edu"
              {...form.getInputProps("email")}
            />
            <PasswordInput
              label="Password"
              placeholder="Your password"
              {...form.getInputProps("password")}
            />
            <Button type="submit" fullWidth mt="xs" loading={submitting}>
              Log In
            </Button>
          </Stack>
        </form>

        <Text c="dimmed" size="sm">
          New here?{" "}
          <Anchor component={Link} to="/register">
            Create an account
          </Anchor>
        </Text>
      </Stack>
    </AuthLayout>
  );
}
