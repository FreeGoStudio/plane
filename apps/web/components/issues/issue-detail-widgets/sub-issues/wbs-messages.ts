// Copyright (c) 2023-present Plane Software, Inc. and contributors
// SPDX-License-Identifier: AGPL-3.0-only
// See the LICENSE file for details.

const messageKeys = {
  "WBS version conflict": "wbs.server_wbs_version_conflict",
  "Active human account required": "wbs.server_active_human_account_required",
  "Workspace membership required": "wbs.server_workspace_membership_required",
  "Project member role required": "wbs.server_project_member_role_required",
  "Confirm the saved requirement version before requesting a draft":
    "wbs.server_confirm_the_saved_requirement_version_before_requesting_a_draft",
  "Invalid idempotency key": "wbs.server_invalid_idempotency_key",
  "Idempotency key already used for another version": "wbs.server_idempotency_key_already_used_for_another_version",
  "Requirement changed; reload and confirm the current version":
    "wbs.server_requirement_changed_reload_and_confirm_the_current_version",
  "A root requirement with a description is required": "wbs.server_a_root_requirement_with_a_description_is_required",
  "WBS skill is unavailable or exceeds the input limit":
    "wbs.server_wbs_skill_is_unavailable_or_exceeds_the_input_limit",
  "An active draft already exists; review it before starting another":
    "wbs.server_an_active_draft_already_exists_review_it_before_starting_another",
  "An analysis of this version already exists": "wbs.server_an_analysis_of_this_version_already_exists",
  "Explicit approve or reject required": "wbs.server_explicit_approve_or_reject_required",
  "Draft version changed": "wbs.server_draft_version_changed",
  "This draft already has a different decision": "wbs.server_this_draft_already_has_a_different_decision",
  "This draft was approved with different task actions":
    "wbs.server_this_draft_was_approved_with_different_task_actions",
  "This draft was approved with different replacement task content":
    "wbs.server_this_draft_was_approved_with_different_replacement_task_content",
  "Draft is not ready for review": "wbs.server_draft_is_not_ready_for_review",
  "A rejection reason is required": "wbs.server_a_rejection_reason_is_required",
  "Use Update WBS to analyze the current PRD before approval":
    "wbs.server_use_update_wbs_to_analyze_the_current_prd_before_approval",
  "Requirement or child tasks changed; reject this draft and regenerate":
    "wbs.server_requirement_or_child_tasks_changed_reject_this_draft_and_regenerate",
  "Draft duplicates an existing child task": "wbs.server_draft_duplicates_an_existing_child_task",
  "Insufficient delegation scope": "wbs.server_insufficient_delegation_scope",
  "Register one delivery directory or its prd.md for WBS; primary prd.md is missing or ambiguous":
    "wbs.server_register_one_delivery_directory_or_its_prd_md_for_wbs_primary_prd_md_is_missing_or_ambiguous",
  "Primary prd.md is empty; complete the implementation requirements before WBS":
    "wbs.server_primary_prd_md_is_empty_complete_the_implementation_requirements_before_wbs",
  "PRD changed; update WBS again": "wbs.server_prd_changed_update_wbs_again",
  "Child tasks changed; update WBS again": "wbs.server_child_tasks_changed_update_wbs_again",
  "A newer WBS analysis exists": "wbs.server_a_newer_wbs_analysis_exists",
  "The adopted PRD no longer matches this analysis": "wbs.server_the_adopted_prd_no_longer_matches_this_analysis",
  "Unable to verify the PRD source; retry after restoring access":
    "wbs.server_unable_to_verify_the_prd_source_retry_after_restoring_access",
  "Unknown child reference": "wbs.server_unknown_child_reference",
  "Every existing child must appear exactly once": "wbs.server_every_existing_child_must_appear_exactly_once",
  "Invalid requirement coverage": "wbs.server_invalid_requirement_coverage",
  "Invalid coverage references": "wbs.server_invalid_coverage_references",
  "A requirement gap needs implementation or investigation work":
    "wbs.server_a_requirement_gap_needs_implementation_or_investigation_work",
  "Invalid change action": "wbs.server_invalid_change_action",
  "Completed tasks must retain their original acceptance":
    "wbs.server_completed_tasks_must_retain_their_original_acceptance",
  "Invalid task references: task ID mismatch": "wbs.server_invalid_task_references_task_id_mismatch",
  "Invalid task references: unknown task dependency": "wbs.server_invalid_task_references_unknown_task_dependency",
  "Invalid task references: acceptance mapping mismatch":
    "wbs.server_invalid_task_references_acceptance_mapping_mismatch",
  "Cyclic dependency": "wbs.server_cyclic_dependency",
  "Explicit confirmation of this exact requirement text is required":
    "wbs.server_explicit_confirmation_of_this_exact_requirement_text_is_required",
  "Confirm the action for every affected started or uncertain task":
    "wbs.server_confirm_the_action_for_every_affected_started_or_uncertain_task",
  "Provide complete reviewed task content when replacing a cancellation":
    "wbs.server_provide_complete_reviewed_task_content_when_replacing_a_cancellation",
  "Replacement task content cannot be blank": "wbs.server_replacement_task_content_cannot_be_blank",
  "Replacement must reference the current requirement criteria":
    "wbs.server_replacement_must_reference_the_current_requirement_criteria",
  "Invalid replacement task content or requirement references":
    "wbs.server_invalid_replacement_task_content_or_requirement_references",
  "Invalid action for the task's development stage": "wbs.server_invalid_action_for_the_task_s_development_stage",
  "Configure a cancelled state before approving cancellations":
    "wbs.server_configure_a_cancelled_state_before_approving_cancellations",
  "Invalid coverage or duplicate IDs": "wbs.server_invalid_coverage_or_duplicate_ids",
  "Invalid task references": "wbs.server_invalid_task_references",
  "Duplicate child task": "wbs.server_duplicate_child_task",
  "Model did not complete": "wbs.server_model_did_not_complete",
  "Dispatch unavailable; automatic retry pending": "wbs.server_dispatch_unavailable_automatic_retry_pending",
  ReadTimeout: "wbs.server_readtimeout",
  ConnectTimeout: "wbs.server_connecttimeout",
  ConnectionError: "wbs.server_connectionerror",
  HTTPError: "wbs.server_httperror",
  ValidationError: "wbs.server_validationerror",
  PermissionDenied: "wbs.server_permissiondenied",
  RuntimeError: "wbs.server_runtimeerror",
  RepositoryError: "wbs.server_repositoryerror",
  "Authentication credentials were not provided.": "wbs.server_authentication_credentials_were_not_provided",
  "You do not have permission to perform this action.": "wbs.server_you_do_not_have_permission_to_perform_this_action",
  "Not found.": "wbs.server_not_found",
  "Confirm this PRD version before applying WBS changes": "wbs.confirm_prd_before_apply",
} as const;

type MessageKey =
  | (typeof messageKeys)[keyof typeof messageKeys]
  | "wbs.server_error_unknown"
  | "wbs.server_missing_prd";

/** Normalize DRF errors and worker diagnostics without discarding unknown details. */
export function wbsMessage(value: unknown): { key: MessageKey; params: Record<string, string>; details?: string } {
  let reason = value;
  if (reason && typeof reason === "object" && "detail" in reason) reason = reason.detail;
  if (Array.isArray(reason) && reason.length === 1) reason = reason[0];
  if (typeof reason === "string") {
    const key = Object.hasOwn(messageKeys, reason) ? messageKeys[reason as keyof typeof messageKeys] : undefined;
    if (key) return { key, params: {} };
    const match = /^Primary prd\.md is missing or unreadable at (.+); no alternative file was selected$/.exec(reason);
    if (match) return { key: "wbs.server_missing_prd", params: { path: match[1] } };
  }
  return {
    key: "wbs.server_error_unknown",
    params: {},
    details: typeof value === "string" ? value : JSON.stringify(value),
  };
}
