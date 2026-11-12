/** Translates known shared-validator messages without changing validation results. */
import type { TTranslationStore } from "./hooks/use-translation";

const validationKeys: Record<string, string> = {
  "Name is required": "validation.name_required",
  "Name must be 50 characters or less": "validation.name_length",
  "Names cannot contain special characters like < > ' \" { } [ ] * ^ ! # %": "validation.name_special",
  "Names can only contain letters, spaces, hyphens, and apostrophes": "validation.name_characters",
  "Display name must be 50 characters or less": "validation.display_name_length",
  "Display name cannot contain special characters like < > ' \" { } [ ] * ^ ! # %": "validation.display_name_special",
  "Display name can only contain letters, numbers, periods, hyphens, and underscores":
    "validation.display_name_characters",
  "Company name is required": "validation.company_name_required",
  "Company name must be 80 characters or less": "validation.company_name_length",
  "Company name cannot contain special characters like < > ' \" { } [ ] * ^ ! # %": "validation.company_name_special",
  "Company name can only contain letters, numbers, spaces, hyphens, and underscores":
    "validation.company_name_characters",
  "Company name must contain at least one letter or number": "validation.company_name_alphanumeric",
  "Workspace name is required": "validation.workspace_name_required",
  "Workspace name must be 80 characters or less": "validation.workspace_name_length",
  "Workspace name cannot contain special characters like < > ' \" { } [ ] * ^ ! # %":
    "validation.workspace_name_special",
  "Workspace name can only contain letters, numbers, spaces, hyphens, and underscores":
    "validation.workspace_name_characters",
  "Workspace name must contain at least one letter or number": "validation.workspace_name_alphanumeric",
  "Slug is required": "validation.slug_required",
  "Slug must be 48 characters or less": "validation.slug_length",
  "Slug cannot contain special characters like < > ' \" { } [ ] * ^ ! # %": "validation.slug_special",
  "Slug can only contain letters, numbers, hyphens, and underscores": "validation.slug_characters",
};

export function translateValidationMessage<T extends boolean | string | undefined>(
  result: T,
  t: TTranslationStore["t"]
): T | string {
  return typeof result === "string" && Object.hasOwn(validationKeys, result) ? t(validationKeys[result]) : result;
}
