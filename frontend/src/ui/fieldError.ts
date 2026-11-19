import { ApiError } from "../api/client";

export function requiredFieldsError(
  message: string,
  fields: { field: string; message?: string }[],
) {
  return new ApiError(
    400,
    "VALIDATION_ERROR",
    message,
    fields.map((entry) => ({
      field: entry.field,
      code: "REQUIRED",
      message: entry.message ?? message,
    })),
  );
}

export function fieldError(error: unknown, field: string) {
  if (error instanceof ApiError) {
    return error.fields.find(
      (entry) => entry.field === field || entry.field.startsWith(field + "."),
    )?.message;
  }
}
