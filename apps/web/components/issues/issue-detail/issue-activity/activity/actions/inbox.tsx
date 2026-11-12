/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { LocalizedText } from "@plane/i18n";
import { observer } from "mobx-react";
// hooks
import { IntakeOutline } from "@makeplane/propel/icons";
import { useIssueDetail } from "@/hooks/store/use-issue-detail";
// components
import { IssueActivityBlockComponent } from "./";
// icons

type TIssueInboxActivity = { activityId: string; ends: "top" | "bottom" | undefined };

export const IssueInboxActivity = observer(function IssueInboxActivity(props: TIssueInboxActivity) {
  const { activityId, ends } = props;
  // hooks
  const {
    activity: { getActivityById },
  } = useIssueDetail();

  const activity = getActivityById(activityId);

  const getInboxActivityMessage = () => {
    switch (activity?.verb) {
      case "-1":
        return "work_item_activity.intake_declined";
      case "0":
        return "work_item_activity.intake_snoozed";
      case "1":
        return "work_item_activity.intake_accepted";
      case "2":
        return "work_item_activity.intake_duplicate";
      default:
        return "work_item_activity.intake_updated";
    }
  };

  if (!activity) return <></>;
  return (
    <IssueActivityBlockComponent
      icon={<IntakeOutline className="h-4 w-4 flex-shrink-0 text-secondary" />}
      activityId={activityId}
      ends={ends}
    >
      <LocalizedText messageKey={getInboxActivityMessage()} />
    </IssueActivityBlockComponent>
  );
});
