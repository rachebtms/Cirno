import { Alert } from "@heroui/react";
import { CircleAlert } from "lucide-react";

export function InlineError({ message }: { message: string | null | undefined }) {
  return message ? (
    <Alert status="danger" role="alert">
      <Alert.Indicator>
        <CircleAlert />
      </Alert.Indicator>
      <Alert.Content>
        <Alert.Description>{message}</Alert.Description>
      </Alert.Content>
    </Alert>
  ) : null;
}
