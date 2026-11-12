/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { LocalizedText } from "@plane/i18n";
import { observer } from "mobx-react";
import { ParentOutline } from "@makeplane/propel/icons";
// hooks
import { useIssueDetail } from "@/hooks/store/use-issue-detail";
// components
import { IssueActivityBlockComponent, IssueLink } from "./";

type TIssueParentActivity = { activityId: string; showIssue?: boolean; ends: "top" | "bottom" | undefined };

export const IssueParentActivity = observer(function IssueParentActivity(props: TIssueParentActivity) {
  const { activityId, showIssue = true, ends } = props;
  // hooks
  const {
    activity: { getActivityById },
  } = useIssueDetail();

  const activity = getActivityById(activityId);

  if (!activity) return <></>;
  return (
    <IssueActivityBlockComponent
      icon={<ParentOutline className="h-3.5 w-3.5 text-secondary" aria-hidden="true" />}
      activityId={activityId}
      ends={ends}
    >
      <LocalizedText
        messageKey={`work_item_activity.parent_${activity.new_value ? "set" : "removed"}_${showIssue ? "issue" : "self"}`}
        components={{
          value: <span className="font-medium text-primary">{activity.new_value || activity.old_value}</span>,
          issue: <IssueLink activityId={activityId} />,
        }}
      />
    </IssueActivityBlockComponent>
  );
});
