/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useTranslation, getUserDisplayName } from "@plane/i18n";
import { observer } from "mobx-react";
import { Avatar } from "@makeplane/propel/components/avatar";
// helpers
import { getFileURL } from "@plane/utils";
// types
import { useMember } from "@/hooks/store/use-member";
import { RemovableChip } from "@/components/common/removable-chip";

type Props = {
  handleRemove: (val: string) => void;
  values: string[];
  editable: boolean | undefined;
};

export const AppliedMembersFilters = observer(function AppliedMembersFilters(props: Props) {
  useTranslation();
  const { handleRemove, values, editable } = props;
  // store hooks
  const {
    workspace: { getWorkspaceMemberDetails },
  } = useMember();

  return (
    <>
      {values.map((memberId) => {
        const memberDetails = getWorkspaceMemberDetails(memberId)?.member;

        if (!memberDetails) return null;

        return (
          <RemovableChip
            key={memberId}
            variant="soft"
            icon={
              <Avatar
                alt={getUserDisplayName(memberDetails)}
                fallback={getUserDisplayName(memberDetails)?.[0]?.toUpperCase()}
                src={getFileURL(memberDetails.avatar_url)}
                size="2xs"
              />
            }
            label={getUserDisplayName(memberDetails)}
            ariaLabel={getUserDisplayName(memberDetails)}
            onRemove={editable ? () => handleRemove(memberId) : undefined}
          />
        );
      })}
    </>
  );
});
