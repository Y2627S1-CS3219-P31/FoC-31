import {
  Anchor,
  Button,
  Group,
  PasswordInput,
  PinInput,
  Stack,
  Text,
  TextInput,
  Title,
} from "@mantine/core";
import { useForm } from "@mantine/form";
import { notifications } from "@mantine/notifications";
import { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { ApiError, authApi } from "../../lib/api";
import { AuthLayout } from "./AuthLayout";

export default function ResetPassword() {
  const navigate = useNavigate();
  const location = useLocation();
  const initialEmail = (location.state as { email?: string } | null)?.email ?? "";
  const [submitting, setSubmitting] = useState(false);
  const [resending, setResending] = useState(false);

  const form = useForm({
    initialValues: { email: initialEmail, code: "", password: "", confirm: "" },
    validate: {
      email: (v) => (/^\S+@\S+$/.test(v) ? null : "Enter a valid email"),
      code: (v) => (/^\d{6}$/.test(v) ? null : "Enter the 6-digit code"),
      password: (v) =>
        v.length >= 8 && /[A-Za-z]/.test(v) && /\d/.test(v)
          ? null
          : "Min 8 characters, with letters and digits",
      confirm: (v, values) => (v === values.password ? null : "Passwords do not match"),
    },
  });

  const handleSubmit = form.onSubmit(async ({ email, code, password }) => {
    setSubmitting(true);
    try {
      const { message } = await authApi.resetPassword(
        email.trim().toLowerCase(),
        code,
        password,
      );
      notifications.show({ color: "green", message });
      navigate("/login", { replace: true });
    } catch (err) {
      const message =
        err instanceof ApiError ? err.message : "Could not reset password.";
      notifications.show({ color: "red", message });
    } finally {
      setSubmitting(false);
    }
  });

  const handleResend = async () => {
    const email = form.values.email.trim().toLowerCase();
    if (!email) {
      form.setFieldError("email", "Enter your email first");
      return;
    }
    setResending(true);
    try {
      const { message } = await authApi.forgotPassword(email);
      notifications.show({ color: "green", message });
    } catch (err) {
      const message =
        err instanceof ApiError ? err.message : "Could not resend the code.";
      notifications.show({ color: "red", message });
    } finally {
      setResending(false);
    }
  };

  return (
    <AuthLayout>
      <Stack gap="md">
        <div>
          <Title order={3}>Reset your password</Title>
          <Text c="dimmed" size="sm">
            Enter the code from your email and choose a new password
          </Text>
        </div>

        <form onSubmit={handleSubmit}>
          <Stack gap="sm">
            <TextInput
              label="NUS Email"
              placeholder="e0123456@u.nus.edu"
              {...form.getInputProps("email")}
            />
            <Stack gap={4}>
              <Text size="sm" fw={500}>
                Reset code
              </Text>
              <PinInput
                length={6}
                oneTimeCode
                type="number"
                {...form.getInputProps("code")}
              />
              {form.errors.code && (
                <Text c="red" size="xs">
                  {form.errors.code}
                </Text>
              )}
            </Stack>
            <PasswordInput
              label="New password"
              placeholder="Min 8 chars, letters + digits"
              {...form.getInputProps("password")}
            />
            <PasswordInput
              label="Confirm new password"
              {...form.getInputProps("confirm")}
            />
            <Button type="submit" fullWidth mt="xs" loading={submitting}>
              Reset password
            </Button>
          </Stack>
        </form>

        <Group justify="space-between">
          <Anchor component="button" type="button" size="sm" onClick={handleResend}>
            {resending ? "Resending..." : "Resend code"}
          </Anchor>
          <Anchor component={Link} to="/login" size="sm">
            Back to login
          </Anchor>
        </Group>
      </Stack>
    </AuthLayout>
  );
}
