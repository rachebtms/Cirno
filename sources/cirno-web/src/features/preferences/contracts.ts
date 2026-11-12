export type ActivityDisplayMode = "auto" | "expanded";
export type ReadingTextSize = "small" | "standard" | "large" | "custom";
export type FileEditDisplayMode = "summary" | "diff" | "collapsed_diff";
export type ThemeMode = "system" | "light" | "dark";
export const MIN_READING_SIZE = 14;
export const MAX_READING_SIZE = 28;
export const DEFAULT_MEMORY_GRAPH_LIMIT = 300;
export interface DisplayPreferences {
  activityMode: ActivityDisplayMode;
  reasoningDetailMode?: "brief" | "detailed";
  toolDetailMode?: "brief" | "detailed";
  readingTextSize: ReadingTextSize;
  customReadingTextSize: number;
  codeWrap: boolean;
  brandLogos: boolean;
  memoryGraphLimit?: number;
  browserNotifications: boolean;
  notificationSound: boolean;
  mutedNotificationCategories?: Array<
    "operations" | "conversations" | "system"
  >;
  fileEditDisplayMode: FileEditDisplayMode;
}
export interface Palette {
  background: string;
  surface: string;
  panel: string;
  text: string;
  muted: string;
  accent: string;
  border: string;
}
export interface ThemePair {
  id: string;
  name: string;
  light: Palette;
  dark: Palette;
}
export interface OwnerPreferences extends DisplayPreferences {
  themeMode: ThemeMode;
  themeId: string;
  customThemes: ThemePair[];
  language: string;
  launcherOrder: string[];
}
export interface PreferencesSnapshot {
  revision: number;
  values: OwnerPreferences;
  themes: ThemePair[];
}
export const DEFAULT_PREFERENCES: DisplayPreferences = {
  activityMode: "auto",
  reasoningDetailMode: "brief",
  toolDetailMode: "brief",
  readingTextSize: "standard",
  customReadingTextSize: 16,
  codeWrap: true,
  brandLogos: true,
  memoryGraphLimit: DEFAULT_MEMORY_GRAPH_LIMIT,
  browserNotifications: false,
  notificationSound: false,
  mutedNotificationCategories: [],
  fileEditDisplayMode: "summary",
};
export const DEFAULT_OWNER_PREFERENCES: OwnerPreferences = {
  ...DEFAULT_PREFERENCES,
  themeId: "cirno-snow",
  themeMode: "system",
  customThemes: [],
  language: "en",
  launcherOrder: [],
};
export const SNOW_THEME: ThemePair = {
  id: "cirno-snow",
  name: "Cirno Snow",
  light: {
    background: "#f7fbff",
    surface: "#edf5fc",
    panel: "#ffffff",
    text: "#183247",
    muted: "#526c80",
    accent: "#087fa3",
    border: "#d0e2ef",
  },
  dark: {
    background: "#0e1b29",
    surface: "#152738",
    panel: "#1b3043",
    text: "#eaf6ff",
    muted: "#a2bdd0",
    accent: "#7bd5f1",
    border: "#304b60",
  },
};
