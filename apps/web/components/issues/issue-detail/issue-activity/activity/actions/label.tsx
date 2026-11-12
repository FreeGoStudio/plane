/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { LocalizedText } from "@plane/i18n";
import { observer } from "mobx-react";
import { LabelsOutline } from "@makeplane/propel/icons";
// hooks
import { useIssueDetail } from "@/hooks/store/use-issue-detail";
import { useLabel } from "@/hooks/store/use-label";
// components
import { IssueActivityBlockComponent, IssueLink, LabelActivityChip } from "./";

type TIssueLabelActivity = { activityId: string; showIssue?: boolean; ends: "top" | "bottom" | undefined };

export const IssueLabelActivity = observer(function IssueLabelActivity(props: TIssueLabelActivity) {
  const { activityId, showIssue = true, ends } = props;
  // hooks
  const {
    activity: { getActivityById },
  } = useIssueDetail();
  const { getLabelById } = useLabel();

  const activity = getActivityById(activityId);
  const oldLabelColor = getLabelById(activity?.old_identifier ?? "")?.color;
  const newLabelColor = getLabelById(activity?.new_identifier ?? "")?.color;

  if (!activity) return <></>;
  return (
    <IssueActivityBlockComponent
      icon={<LabelsOutline height={14} width={14} className="text-secondary" />}
      activityId={activityId}
      ends={ends}
    >
      <LocalizedText
        messageKey={`work_item_activity.label_${activity.old_value === "" ? "added" : "removed"}_${showIssue ? "issue" : "self"}`}
        components={{
          value: (
            <LabelActivityChip
              name={activity.old_value === "" ? activity.new_value : activity.old_value}
              color={activity.old_value === "" ? newLabelColor : oldLabelColor}
            />
          ),
          issue: <IssueLink activityId={activityId} />,
        }}
      />
    </IssueActivityBlockComponent>
  );
});
