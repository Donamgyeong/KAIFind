import type { Building, Category } from "./types";
import { useRemote } from "./useRemote";

export function useBuildings(includePostedCount = false) {
  return useRemote<{ items: Building[] }>(
    includePostedCount ? "/buildings?includePostedCount=true" : "/buildings",
    true,
  );
}

export function useCategories() {
  return useRemote<{ items: Category[] }>("/categories", true);
}
