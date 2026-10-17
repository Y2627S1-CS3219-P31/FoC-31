// AI-assisted (OpenCode + Claude): OTP verification screen. In dev the code is
// printed to the user-service logs (OTP_DEV_MODE). Reviewed by authors.
import {
  Anchor,
  Button,
  Group,
  PinInput,
  Stack,
  Text,
  TextInput,
  Title,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { ApiError, authApi } from "../../lib/api";
import { AuthLayout } from "./AuthLayout";

export default function VerifyOtp() {
  const navigate = useNavigate();
  const location = useLocation();
  const initialEmail = (location.state as { email?: string } | null)?.email ?? "";

  const [email, setEmail] = useState(initialEmail);
  const [code, setCode] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [resending, setResending] = useState(false);

  const handleVerify = async () => {
    if (!email || code.length !== 6) {
      notifications.show({ color: "red", message: "Enter email and 6-digit code" });
      return;
    }
    setSubmitting(true);
    try {
      await authApi.verifyOtp(email.trim().toLowerCase(), code);
      notifications.show({
        color: "green",
        message: "Email verified — you can now log in.",
      });
      navigate("/login", { state: { from: "/suppliers" } });
    } catch (err) {
      const message =
        err instanceof ApiError ? err.message : "Verification failed.";
      notifications.show({ color: "red", message });
    } finally {
      setSubmitting(false);
    }
  };

  const handleResend = async () => {
    if (!email) {
      notifications.show({ color: "red", message: "Enter your email first" });
      return;
    }
    setResending(true);
    try {
      await authApi.resendOtp(email.trim().toLowerCase());
      notifications.show({ color: "green", message: "A new code was sent." });
    } catch (err) {
      const message =
        err instanceof ApiError ? err.message : "Could not resend code.";
      notifications.show({ color: "red", message });
    } finally {
      setResending(false);
    }
  };

  return (
    <AuthLayout>
      <Stack gap="md">
        <div>
          <Title order={3}>Verify your email</Title>
          <Text c="dimmed" size="sm">
            Enter the 6-digit code sent to your NUS email
          </Text>
        </div>

        <TextInput
          label="NUS Email"
          placeholder="e0123456@u.nus.edu"
          value={email}
          onChange={(e) => setEmail(e.currentTarget.value)}
        />

        <Stack gap={4}>
          <Text size="sm" fw={500}>
            Verification code
          </Text>
          <PinInput
            length={6}
            oneTimeCode
            type="number"
            value={code}
            onChange={setCode}
          />
        </Stack>

        <Button onClick={handleVerify} fullWidth loading={submitting}>
          Verify
        </Button>

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
