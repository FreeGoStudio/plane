/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useTranslation, getUserDisplayName } from "@plane/i18n";
import { Command } from "cmdk";
import { observer } from "mobx-react";
// plane imports

import { Avatar } from "@makeplane/propel/components/avatar";
import { getFileURL } from "@plane/utils";
// hooks
import { useMember } from "@/hooks/store/use-member";
// local imports
import { PowerKModalCommandItem } from "../ui/modal/command-item";

type Props = {
  handleSelect: (assigneeId: string) => void;
  heading?: string;
  userIds: string[] | undefined;
  value: string[];
};

export const PowerKMembersMenu = observer(function PowerKMembersMenu(props: Props) {
  useTranslation();
  const { handleSelect, heading, userIds, value } = props;
  // store hooks
  const { getUserDetails } = useMember();

  return (
    <Command.Group heading={heading}>
      {userIds?.map((memberId) => {
        const memberDetails = getUserDetails(memberId);
        if (!memberDetails) return;

        return (
          <PowerKModalCommandItem
            key={memberId}
            iconNode={
              <Avatar
                alt={getUserDisplayName(memberDetails)}
                fallback={getUserDisplayName(memberDetails)?.[0]?.toUpperCase()}
                src={getFileURL(memberDetails?.avatar_url ?? "")}
                size="xs"
              />
            }
            isSelected={value.includes(memberId)}
            label={getUserDisplayName(memberDetails)}
            onSelect={() => handleSelect(memberId)}
          />
        );
      })}
    </Command.Group>
  );
});
