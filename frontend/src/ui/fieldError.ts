import { ApiError } from "../api/client";

export function fieldError(error: unknown, field: string) {
  if (error instanceof ApiError) {
    return error.fields.find(
      (entry) => entry.field === field || entry.field.startsWith(field + "."),
    )?.message;
  }
}
