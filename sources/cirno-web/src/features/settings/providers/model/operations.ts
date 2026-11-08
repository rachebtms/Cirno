export interface ProviderOperation {
  provider: string;
  action: "save" | "create" | "login" | "logout";
}
