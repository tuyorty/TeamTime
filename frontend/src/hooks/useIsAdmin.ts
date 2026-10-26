import { useMeta } from "@/api/queries";

export function useIsAdmin(): boolean {
  return useMeta().data?.is_admin ?? false;
}
