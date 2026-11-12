/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { LocalizedText, useTranslation } from "@plane/i18n";
import { observer } from "mobx-react";
import { PriorityOutline } from "@makeplane/propel/icons";
// hooks
import { useIssueDetail } from "@/hooks/store/use-issue-detail";
// components
import { IssueActivityBlockComponent, IssueLink } from "./";

type TIssuePriorityActivity = { activityId: string; showIssue?: boolean; ends: "top" | "bottom" | undefined };

export const IssuePriorityActivity = observer(function IssuePriorityActivity(props: TIssuePriorityActivity) {
  const { t } = useTranslation();
  const { activityId, showIssue = true, ends } = props;
  // hooks
  const {
    activity: { getActivityById },
  } = useIssueDetail();

  const activity = getActivityById(activityId);

  if (!activity) return <></>;
  return (
    <IssueActivityBlockComponent
      icon={<PriorityOutline className="h-3.5 w-3.5 text-secondary" aria-hidden="true" />}
      activityId={activityId}
      ends={ends}
    >
      <LocalizedText
        messageKey={`work_item_activity.priority_${showIssue ? "issue" : "self"}`}
        components={{
          value: (
            <span className="font-medium text-primary">
              {["urgent", "high", "medium", "low", "none"].includes(activity.new_value ?? "")
                ? t(`issue.priority.${activity.new_value}`)
                : activity.new_value}
            </span>
          ),
          issue: <IssueLink activityId={activityId} />,
        }}
      />
    </IssueActivityBlockComponent>
  );
});
