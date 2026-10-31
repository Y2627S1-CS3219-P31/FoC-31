import { Anchor, Button, Stack, Text, TextInput, Title } from "@mantine/core";
import { useForm } from "@mantine/form";
import { notifications } from "@mantine/notifications";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ApiError, authApi } from "../../lib/api";
import { AuthLayout } from "./AuthLayout";

export default function ForgotPassword() {
  const navigate = useNavigate();
  const [submitting, setSubmitting] = useState(false);

  const form = useForm({
    initialValues: { email: "" },
    validate: {
      email: (v) => (/^\S+@\S+$/.test(v) ? null : "Enter a valid email"),
    },
  });

  const handleSubmit = form.onSubmit(async ({ email }) => {
    const normalised = email.trim().toLowerCase();
    setSubmitting(true);
    try {
      const { message } = await authApi.forgotPassword(normalised);
      notifications.show({ color: "green", message });
      navigate("/reset-password", { state: { email: normalised } });
    } catch (err) {
      const message =
        err instanceof ApiError ? err.message : "Could not send a reset code.";
      notifications.show({ color: "red", message });
    } finally {
      setSubmitting(false);
    }
  });

  return (
    <AuthLayout>
      <Stack gap="md">
        <div>
          <Title order={3}>Forgot your password?</Title>
          <Text c="dimmed" size="sm">
            We'll email a 6-digit reset code to your NUS email
          </Text>
        </div>

        <form onSubmit={handleSubmit}>
          <Stack gap="sm">
            <TextInput
              label="NUS Email"
              placeholder="e0123456@u.nus.edu"
              {...form.getInputProps("email")}
            />
            <Button type="submit" fullWidth mt="xs" loading={submitting}>
              Send reset code
            </Button>
          </Stack>
        </form>

        <Anchor component={Link} to="/login" size="sm">
          Back to login
        </Anchor>
      </Stack>
    </AuthLayout>
  );
}
