import { Button } from "@heroui/react";
import { useRef, useState } from "react";
import { AutomationEditDialog } from "@/features/automations/edit/AutomationEditDialog";
import { AutomationDeleteDialog } from "@/features/automations/ui/AutomationDeleteDialog";
import type {
  AutomationUpdatePayload,
  SessionAutomationJob,
} from "@/lib/contracts/automations";
import { useTheme } from "@/hooks/useTheme";

const initial: SessionAutomationJob = {
  id: "daily-research",
  name: "Research checkpoint",
  enabled: true,
  schedule: { kind: "every", every_ms: 62_500 },
  payload: { message: "Review the latest experiment and record its findings." },
  state: {},
};

export function AutomationsFixture() {
  useTheme();
  const [job, setJob] = useState(initial);
  const [editing, setEditing] = useState(false),
    [deleting, setDeleting] = useState(false);
  const [writes, setWrites] = useState<AutomationUpdatePayload[]>([]);
  const failSave = useRef(true),
    failDelete = useRef(true);
  return (
    <main className="min-h-screen bg-background p-4 text-foreground sm:p-8">
      <h1 className="mb-6 text-xl font-semibold">Automations</h1>
      <div className="flex flex-wrap gap-3">
        <Button onPress={() => setEditing(true)}>Edit automation</Button>
        <Button variant="secondary" onPress={() => setDeleting(true)}>
          Delete automation
        </Button>
        <Button
          variant="ghost"
          onPress={() =>
            setJob((previous) => ({ ...previous, name: "Updated on server" }))
          }
        >
          Refresh metadata
        </Button>
      </div>
      <output data-testid="automation-writes">{JSON.stringify(writes)}</output>
      <AutomationEditDialog
        job={editing ? job : null}
        saving={false}
        onOpenChange={setEditing}
        onSave={async (_job, values) => {
          if (failSave.current) {
            failSave.current = false;
            throw new Error("Fixture automation save failed");
          }
          setWrites((previous) => [...previous, values]);
          setEditing(false);
        }}
      />
      <AutomationDeleteDialog
        job={deleting ? job : null}
        deleting={false}
        onOpenChange={setDeleting}
        onConfirm={async () => {
          if (failDelete.current) {
            failDelete.current = false;
            throw new Error("Fixture automation delete failed");
          }
          setDeleting(false);
        }}
      />
    </main>
  );
}
