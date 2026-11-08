import { Button } from "@heroui/react";
import { useState } from "react";
import { ChannelFields } from "@/features/channels/ui/fields/ChannelFields";
import { channelValuesForSubmit } from "@/features/channels/model/fieldValues";
import { focusFirstChannelFieldError } from "@/features/channels/model/fieldValidation";
import { useTheme } from "@/hooks/useTheme";
import type { ChannelConfigField } from "@/channel-plugins/catalog";
import "@/features/channels/channels.css";
const fields: ChannelConfigField[] = [
  {
    key: "region",
    label: "Region",
    options: [
      { value: "", label: "Default" },
      { value: "eu", label: "Europe" },
      { value: "us", label: "United States" },
    ],
  },
  { key: "useProxy", label: "Use proxy", control: "switch", kind: "bool" },
  { key: "token", label: "API token", secret: true },
  { key: "options", label: "Connection options", kind: "json" },
];
export function ChannelFieldsFixture() {
  useTheme();
  const [values, setValues] = useState<Record<string, string>>({
      region: "eu",
      useProxy: "true",
      options: '{\n  "timeout": 30\n}',
    }),
    [visible, setVisible] = useState<Record<string, boolean>>({}),
    [cleared, setCleared] = useState(new Set<string>()),
    [touched, setTouched] = useState(new Set<string>()),
    [errors, setErrors] = useState<Record<string, string>>({});
  return (
    <main className="min-h-screen bg-background p-4 text-foreground sm:p-8">
      <div className="mx-auto max-w-xl space-y-6">
        <h1 className="text-xl font-semibold">Connection fields</h1>
        <ChannelFields
          fields={fields}
          values={values}
          configuredFields={new Set(["token"])}
          visibleSecrets={visible}
          clearedSecrets={cleared}
          errors={errors}
          showSecretActions
          onChange={(key, value) => {
            setValues((previous) => ({ ...previous, [key]: value }));
            setTouched((previous) => new Set(previous).add(key));
            setErrors({});
          }}
          onToggleSecret={(key) =>
            setVisible((previous) => ({ ...previous, [key]: !previous[key] }))
          }
          onClearSecret={(key, clear) =>
            setCleared((previous) => {
              const next = new Set(previous);
              if (clear) next.add(key);
              else next.delete(key);
              return next;
            })
          }
        />
        <Button
          variant="secondary"
          onPress={() => {
            const next = {
              region: "Choose a connection region",
              token: "API token rejected",
            };
            setErrors(next);
            focusFirstChannelFieldError(next);
          }}
        >
          Validate fields
        </Button>
        <output hidden data-testid="field-payload">
          {JSON.stringify(
            channelValuesForSubmit(fields, values, touched, cleared),
          )}
        </output>
      </div>
    </main>
  );
}
