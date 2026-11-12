/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { LocalizedText } from "@plane/i18n";
import { observer } from "mobx-react";
import { CalendarOutline } from "@makeplane/propel/icons";
// hooks
import { useDateFormatter } from "@plane/utils";
import { useIssueDetail } from "@/hooks/store/use-issue-detail";
// components
import { IssueActivityBlockComponent, IssueLink } from "./";
// helpers

type TIssueStartDateActivity = { activityId: string; showIssue?: boolean; ends: "top" | "bottom" | undefined };

export const IssueStartDateActivity = observer(function IssueStartDateActivity(props: TIssueStartDateActivity) {
  const { renderFormattedDate } = useDateFormatter();
  const { activityId, showIssue = true, ends } = props;
  // hooks
  const {
    activity: { getActivityById },
  } = useIssueDetail();

  const activity = getActivityById(activityId);

  if (!activity) return <></>;
  return (
    <IssueActivityBlockComponent
      icon={<CalendarOutline width={14} height={14} className="text-secondary" aria-hidden="true" />}
      activityId={activityId}
      ends={ends}
    >
      <LocalizedText
        messageKey={`work_item_activity.start_date_${activity.new_value ? "set" : "removed"}_${showIssue ? "issue" : "self"}`}
        components={{
          value: <span className="font-medium text-primary">{renderFormattedDate(activity.new_value)}</span>,
          issue: <IssueLink activityId={activityId} />,
        }}
      />
    </IssueActivityBlockComponent>
  );
});
