import { Card } from "@heroui/react";
import { SkeletonStatus } from "@/ui/feedback/SkeletonStatus";
export function ChannelSkeleton({ label }: { label: string }) {
  return (
    <SkeletonStatus label={label} className="channel-cards">
      {Array.from({ length: 4 }, (_, index) => (
        <Card key={index}>
          <Card.Content className="channel-placeholder">
            <span />
            <div>
              <span />
              <span />
            </div>
            <span />
          </Card.Content>
        </Card>
      ))}
    </SkeletonStatus>
  );
}
