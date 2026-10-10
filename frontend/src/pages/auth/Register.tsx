// AI-assisted (OpenCode + Claude): registration screen. On success it routes
// to OTP verification. Reviewed by authors.
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
import { Link, useNavigate } from "react-router-dom";
import { ApiError, authApi } from "../../lib/api";
import { AuthLayout } from "./AuthLayout";

export default function Register() {
  const navigate = useNavigate();
  const [submitting, setSubmitting] = useState(false);

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
      displayName: (v) => (v.trim().length > 0 ? null : "Display name required"),
      contactNumber: (v) =>
        v === "" || /^[89]\d{7}$/.test(v)
          ? null
          : "SG mobile: 8 digits starting 8 or 9",
    },
  });

  const handleSubmit = form.onSubmit(async (values) => {
    setSubmitting(true);
    try {
      await authApi.register({
        email: values.email.trim().toLowerCase(),
        password: values.password,
        display_name: values.displayName.trim(),
        contact_number: values.contactNumber || null,
      });
      notifications.show({
        color: "green",
        message: "Account created. Check your email for a verification code.",
      });
      navigate("/verify-otp", {
        state: { email: values.email.trim().toLowerCase() },
      });
    } catch (err) {
      const message =
        err instanceof ApiError
          ? err.message
          : "Registration failed. Try again.";
      notifications.show({ color: "red", message });
    } finally {
      setSubmitting(false);
    }
  });

  return (
    <AuthLayout>
      <Stack gap="md">
        <div>
          <Title order={3}>Create your account</Title>
          <Text c="dimmed" size="sm">
            Sign up with your NUS account to get started
          </Text>
        </div>

        <Tabs
          value="signup"
          onChange={(v) => v === "login" && navigate("/login")}
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
            <TextInput
              label="Display name"
              placeholder="Your name"
              {...form.getInputProps("displayName")}
            />
            <TextInput
              label="Contact number (optional)"
              placeholder="9XXXXXXX"
              {...form.getInputProps("contactNumber")}
            />
            <PasswordInput
              label="Password"
              placeholder="Min 8 chars, letters + digits"
              {...form.getInputProps("password")}
            />
            <Button type="submit" fullWidth mt="xs" loading={submitting}>
              Sign Up
            </Button>
          </Stack>
        </form>

        <Text c="dimmed" size="sm">
          Already have an account?{" "}
          <Anchor component={Link} to="/login">
            Log in
          </Anchor>
        </Text>
      </Stack>
    </AuthLayout>
  );
}
