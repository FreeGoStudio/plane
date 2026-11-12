/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useEffect } from "react";
import type { ReactElement } from "react";
import { LocalizedText, useTranslation } from "@plane/i18n";
import { observer } from "mobx-react";
import { useParams } from "next/navigation";
// store hooks
// icons
import {
  ArchiveOutline,
  AttachOutline,
  CalendarOutline,
  ChatOutline,
  CyclesOutline,
  DuplicateOfOutline,
  EpicOutline,
  EstimateOutline,
  GridOutline,
  IntakeOutline,
  LabelsOutline,
  LinkOutline,
  MembersOutline,
  ModuleOutline,
  PriorityMedium,
  RelatesToOutline,
  WorkItemsOutline,
} from "@makeplane/propel/icons";
import { BlockedIcon, BlockerIcon } from "@plane/blocks/icons";
import { Tooltip } from "@makeplane/propel/components/tooltip";
import type { IIssueActivity } from "@plane/types";
import { DateDisplay, generateWorkItemLink } from "@plane/utils";
// helpers
import { useLabel } from "@/hooks/store/use-label";
import { usePlatformOS } from "@/hooks/use-platform-os";
// types

/** Renders the original work item identity or a localized deleted-item fallback. */
export function IssueLink({ activity }: { activity: IIssueActivity }) {
  // router params
  const { workspaceSlug } = useParams();
  const { t } = useTranslation();
  const { isMobile } = usePlatformOS();

  const workItemLink = generateWorkItemLink({
    workspaceSlug: workspaceSlug?.toString() ?? activity.workspace_detail?.slug,
    projectId: activity?.project,
    issueId: activity?.issue,
    projectIdentifier: activity?.project_detail?.identifier,
    sequenceId: activity?.issue_detail?.sequence_id,
  });

  return (
    <Tooltip
      label={activity?.issue_detail ? activity.issue_detail.name : t("work_item_activity.deleted_item_hint")}
      layout="stacked"
      disabled={isMobile}
    >
      {activity?.issue_detail ? (
        <a
          aria-disabled={activity.issue === null}
          href={workItemLink}
          target={activity.issue === null ? "_self" : "_blank"}
          rel={activity.issue === null ? "" : "noopener noreferrer"}
          className="inline items-center gap-1 font-medium text-primary hover:underline"
        >
          <span className="whitespace-nowrap">{`${activity.project_detail.identifier}-${activity.issue_detail.sequence_id}`}</span>{" "}
          <span className="font-regular break-all">{activity.issue_detail?.name}</span>
        </a>
      ) : (
        <span className="inline-flex items-center gap-1 font-medium whitespace-nowrap text-primary">
          {t("common.work_item")}
        </span>
      )}
    </Tooltip>
  );
}

function UserLink({ activity }: { activity: IIssueActivity }) {
  // router params
  const { workspaceSlug } = useParams();

  return (
    <a
      href={`/${workspaceSlug ?? activity.workspace_detail?.slug}/profile/${
        activity.new_identifier ?? activity.old_identifier
      }`}
      target="_blank"
      rel="noopener noreferrer"
      className="inline-flex items-center font-medium text-primary hover:underline"
    >
      {activity.new_value && activity.new_value !== "" ? activity.new_value : activity.old_value}
    </a>
  );
}

const LabelPill = observer(function LabelPill({ labelId, workspaceSlug }: { labelId: string; workspaceSlug: string }) {
  // store hooks
  const { workspaceLabels, fetchWorkspaceLabels } = useLabel();

  useEffect(() => {
    if (!workspaceLabels) fetchWorkspaceLabels(workspaceSlug);
  }, [fetchWorkspaceLabels, workspaceLabels, workspaceSlug]);

  return (
    <span
      className="h-1.5 w-1.5 flex-shrink-0 rounded-full"
      style={{
        backgroundColor: workspaceLabels?.find((l) => l.id === labelId)?.color ?? "#000000",
      }}
      aria-hidden="true"
    />
  );
});

/** Localizes each activity sentence while keeping dates, user values and navigation as React nodes. */
function LocalizedActivity({
  activity,
  showIssue,
  workspaceSlug,
}: {
  activity: IIssueActivity;
  showIssue: boolean;
  workspaceSlug: string;
}) {
  const { t } = useTranslation();
  const field = activity.field;
  const suffix = showIssue ? "issue" : "self";
  let key = "";
  let value: ReactElement = (
    <span className="font-medium break-all text-primary">{activity.new_value || activity.old_value}</span>
  );
  switch (field) {
    case "assignees":
      key = `work_item_activity.assignee_${activity.old_value === "" ? "added" : "removed"}_${suffix}`;
      value = <UserLink activity={activity} />;
      break;
    case "archived_at":
      key = `profile_activity.${activity.new_value === "restore" ? "restored" : "archived"}`;
      break;
    case "attachment":
      key = `work_item_activity.attachment_${activity.verb === "created" ? "uploaded" : "removed"}_${suffix}`;
      break;
    case "description":
    case "state":
      key = `work_item_activity.${field}_${suffix}`;
      break;
    case "estimate_point":
    case "parent":
      key = `work_item_activity.${field === "parent" ? "parent" : "estimate"}_${activity.new_value ? "set" : "removed"}_${suffix}`;
      break;
    case "epic":
      key = `profile_activity.${activity.verb === "created" ? "created" : activity.verb === "converted" ? "converted_to_work_item" : "deleted"}`;
      break;
    case "cycles":
    case "modules": {
      const removed = activity.verb !== "created" && activity.verb !== "updated";
      key = `profile_activity.${field}_${activity.verb === "created" ? "added" : removed ? "removed" : "updated"}`;
      value = (
        <a
          href={`/${workspaceSlug}/projects/${activity.project}/${field}/${removed ? activity.old_identifier : activity.new_identifier}`}
          target="_blank"
          rel="noopener noreferrer"
          className="inline items-center gap-1 font-medium text-primary hover:underline"
        >
          <span className="break-all">{removed ? activity.old_value : activity.new_value}</span>
        </a>
      );
      break;
    }
    case "name":
      key = "profile_activity.name";
      value = <span className="break-all">{activity.new_value}</span>;
      break;
    case "priority": {
      key = `work_item_activity.priority_${suffix}`;
      const priority = activity.new_value || "none";
      value = (
        <span className="font-medium text-primary">
          {priority === "none"
            ? t("none")
            : ["urgent", "high", "medium", "low"].includes(priority)
              ? t(`issue.priority.${priority}`)
              : priority}
        </span>
      );
      break;
    }
    case "relates_to":
    case "blocking":
    case "blocked_by":
    case "duplicate":
      key = `profile_activity.${field}_${activity.old_value === "" ? "added" : "removed"}`;
      value = (
        <span className="font-medium whitespace-nowrap text-primary">
          {activity.old_value === "" ? activity.new_value : activity.old_value}
        </span>
      );
      break;
    case "start_date":
    case "target_date":
      key = `work_item_activity.${field}_${activity.new_value ? "set" : "removed"}_${suffix}`;
      value = (
        <span className="font-medium whitespace-nowrap text-primary">
          {activity.new_value && <DateDisplay value={activity.new_value} />}
        </span>
      );
      break;
    case "inbox": {
      const actions: Record<string, string> = { "-1": "declined", "0": "snoozed", "1": "accepted", "2": "duplicate" };
      key = `profile_activity.intake_${actions[activity.verb] ?? "updated"}`;
      break;
    }
    default:
      return null;
  }
  return (
    <LocalizedText
      messageKey={key}
      components={{
        value,
        issue:
          showIssue || field === "archived_at" || field === "epic" ? (
            <IssueLink activity={activity} />
          ) : (
            <LocalizedText messageKey="common.work_item" />
          ),
      }}
    />
  );
}

const activityDetails: {
  [key: string]: {
    message: (activity: IIssueActivity, showIssue: boolean, workspaceSlug: string) => React.ReactNode;
    icon: React.ReactNode;
  };
} = {
  assignees: {
    message: (activity, showIssue, workspaceSlug) => (
      <LocalizedActivity activity={activity} showIssue={showIssue} workspaceSlug={workspaceSlug} />
    ),
    icon: <MembersOutline width={12} height={12} className="text-secondary" aria-hidden="true" />,
  },
  archived_at: {
    message: (activity, showIssue, workspaceSlug) => (
      <LocalizedActivity activity={activity} showIssue={showIssue} workspaceSlug={workspaceSlug} />
    ),
    icon: <ArchiveOutline width={12} height={12} className="text-secondary" aria-hidden="true" />,
  },
  attachment: {
    message: (activity, showIssue, workspaceSlug) => (
      <LocalizedActivity activity={activity} showIssue={showIssue} workspaceSlug={workspaceSlug} />
    ),
    icon: <AttachOutline width={12} height={12} className="text-secondary" aria-hidden="true" />,
  },
  description: {
    message: (activity, showIssue, workspaceSlug) => (
      <LocalizedActivity activity={activity} showIssue={showIssue} workspaceSlug={workspaceSlug} />
    ),
    icon: <ChatOutline width={12} height={12} className="text-secondary" aria-hidden="true" />,
  },
  estimate_point: {
    message: (activity, showIssue, workspaceSlug) => (
      <LocalizedActivity activity={activity} showIssue={showIssue} workspaceSlug={workspaceSlug} />
    ),
    icon: <EstimateOutline width={12} height={12} className="text-secondary" aria-hidden="true" />,
  },
  issue: {
    message: (activity) => (
      <LocalizedText
        messageKey={`profile_activity.${activity.verb === "created" ? "created" : activity.verb === "converted" ? "converted_to_epic" : "deleted"}`}
        components={{ issue: <IssueLink activity={activity} /> }}
      />
    ),
    icon: <WorkItemsOutline width={12} height={12} className="text-secondary" aria-hidden="true" />,
  },
  epic: {
    message: (activity, showIssue, workspaceSlug) => (
      <LocalizedActivity activity={activity} showIssue={showIssue} workspaceSlug={workspaceSlug} />
    ),
    icon: <EpicOutline width={12} height={12} className="text-secondary" aria-hidden="true" />,
  },
  labels: {
    message: (activity, showIssue, workspaceSlug) => (
      <LocalizedText
        messageKey={`work_item_activity.label_${activity.old_value === "" ? "added" : "removed"}_${showIssue ? "issue" : "self"}`}
        components={{
          value: (
            <span className="inline-flex items-center gap-2 rounded-full border border-strong px-2 py-0.5 text-caption-sm-regular">
              <LabelPill
                labelId={(activity.old_value === "" ? activity.new_identifier : activity.old_identifier) ?? ""}
                workspaceSlug={workspaceSlug}
              />
              <span className="line-clamp-1 flex-shrink font-medium break-all text-primary">
                {activity.old_value === "" ? activity.new_value : activity.old_value}
              </span>
            </span>
          ),
          issue: <IssueLink activity={activity} />,
        }}
      />
    ),
    icon: <LabelsOutline width={12} height={12} className="text-secondary" aria-hidden="true" />,
  },
  link: {
    message: (activity, showIssue) => (
      <LocalizedText
        messageKey={`work_item_activity.link_${activity.verb === "created" ? "added" : activity.verb === "updated" ? "updated" : "removed"}_${showIssue ? "issue" : "self"}`}
        components={{
          value: (
            <a
              href={`${activity.verb === "created" ? activity.new_value : activity.old_value}`}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 font-medium text-primary hover:underline"
            >
              <LocalizedText messageKey="link" />
            </a>
          ),
          issue: <IssueLink activity={activity} />,
        }}
      />
    ),
    icon: <LinkOutline width={12} height={12} className="text-secondary" aria-hidden="true" />,
  },
  cycles: {
    message: (activity, showIssue, workspaceSlug) => (
      <LocalizedActivity activity={activity} showIssue={showIssue} workspaceSlug={workspaceSlug} />
    ),
    icon: <CyclesOutline height={12} width={12} className="text-secondary" aria-hidden="true" />,
  },
  modules: {
    message: (activity, showIssue, workspaceSlug) => (
      <LocalizedActivity activity={activity} showIssue={showIssue} workspaceSlug={workspaceSlug} />
    ),
    icon: <ModuleOutline className="h-3 w-3 !text-secondary" aria-hidden="true" />,
  },
  name: {
    message: (activity, showIssue, workspaceSlug) => (
      <LocalizedActivity activity={activity} showIssue={showIssue} workspaceSlug={workspaceSlug} />
    ),
    icon: <ChatOutline width={12} height={12} className="text-secondary" aria-hidden="true" />,
  },
  parent: {
    message: (activity, showIssue, workspaceSlug) => (
      <LocalizedActivity activity={activity} showIssue={showIssue} workspaceSlug={workspaceSlug} />
    ),
    icon: <MembersOutline className="h-3 w-3 !text-secondary" aria-hidden="true" />,
  },
  priority: {
    message: (activity, showIssue, workspaceSlug) => (
      <LocalizedActivity activity={activity} showIssue={showIssue} workspaceSlug={workspaceSlug} />
    ),
    icon: <PriorityMedium width={12} height={12} className="text-secondary" aria-hidden="true" />,
  },
  relates_to: {
    message: (activity, showIssue, workspaceSlug) => (
      <LocalizedActivity activity={activity} showIssue={showIssue} workspaceSlug={workspaceSlug} />
    ),
    icon: <RelatesToOutline height="12" width="12" className="text-secondary" />,
  },
  blocking: {
    message: (activity, showIssue, workspaceSlug) => (
      <LocalizedActivity activity={activity} showIssue={showIssue} workspaceSlug={workspaceSlug} />
    ),
    icon: <BlockerIcon height="12" width="12" className="text-secondary" />,
  },
  blocked_by: {
    message: (activity, showIssue, workspaceSlug) => (
      <LocalizedActivity activity={activity} showIssue={showIssue} workspaceSlug={workspaceSlug} />
    ),
    icon: <BlockedIcon height="12" width="12" className="text-secondary" />,
  },
  duplicate: {
    message: (activity, showIssue, workspaceSlug) => (
      <LocalizedActivity activity={activity} showIssue={showIssue} workspaceSlug={workspaceSlug} />
    ),
    icon: <DuplicateOfOutline width={12} height={12} className="text-secondary" />,
  },
  state: {
    message: (activity, showIssue, workspaceSlug) => (
      <LocalizedActivity activity={activity} showIssue={showIssue} workspaceSlug={workspaceSlug} />
    ),
    icon: <GridOutline width={12} height={12} className="text-secondary" aria-hidden="true" />,
  },
  start_date: {
    message: (activity, showIssue, workspaceSlug) => (
      <LocalizedActivity activity={activity} showIssue={showIssue} workspaceSlug={workspaceSlug} />
    ),
    icon: <CalendarOutline width={12} height={12} className="text-secondary" aria-hidden="true" />,
  },
  target_date: {
    message: (activity, showIssue, workspaceSlug) => (
      <LocalizedActivity activity={activity} showIssue={showIssue} workspaceSlug={workspaceSlug} />
    ),
    icon: <CalendarOutline width={12} height={12} className="text-secondary" aria-hidden="true" />,
  },
  inbox: {
    message: (activity, showIssue, workspaceSlug) => (
      <LocalizedActivity activity={activity} showIssue={showIssue} workspaceSlug={workspaceSlug} />
    ),
    icon: <IntakeOutline className="size-3 text-secondary" aria-hidden="true" />,
  },
};

export function ActivityIcon({ activity }: { activity: IIssueActivity }) {
  return <>{activityDetails[activity.field as keyof typeof activityDetails]?.icon}</>;
}

type ActivityMessageProps = {
  activity: IIssueActivity;
  showIssue?: boolean;
};

export function ActivityMessage({ activity, showIssue = false }: ActivityMessageProps) {
  // router params
  const { workspaceSlug } = useParams();
  const activityField = activity.field ?? "issue";

  return (
    <>
      {activityDetails[activityField as keyof typeof activityDetails]?.message(
        activity,
        showIssue,
        workspaceSlug ? workspaceSlug.toString() : (activity.workspace_detail?.slug ?? "")
      )}
    </>
  );
}
