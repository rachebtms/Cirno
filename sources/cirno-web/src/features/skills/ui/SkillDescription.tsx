import { Button } from "@heroui/react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
export function SkillDescription({ content }: { content: string }) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(false);
  return (
    <div className="skill-description">
      <p data-expanded={expanded || content.length <= 240}>{content}</p>
      {content.length > 240 && (
        <Button variant="ghost" size="sm" aria-expanded={expanded} onPress={() => setExpanded(!expanded)}>
          {t(`settings.skills.${expanded ? "showLess" : "showMore"}`)}
        </Button>
      )}
    </div>
  );
}
