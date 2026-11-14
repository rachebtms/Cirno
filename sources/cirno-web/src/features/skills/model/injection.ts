export interface SkillInjectionSettings {
  names: readonly string[];
  saving: boolean;
  error?: string;
  setSelected: (name: string, selected: boolean) => void;
  retry: () => void;
}
