/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useTranslation } from "@plane/i18n";
import { useMemo } from "react";
import { observer } from "mobx-react";
import type { Control, UseFormSetValue } from "react-hook-form";
import { Controller } from "react-hook-form";
import { CalendarOutline, PreferencesOutline } from "@makeplane/propel/icons";
// plane package imports
import { ANALYTICS_X_AXIS_VALUES, ANALYTICS_Y_AXIS_VALUES } from "@plane/constants";
import type { IAnalyticsParams } from "@plane/types";
import { ChartYAxisMetric } from "@plane/types";
import { cn } from "@plane/utils";
// plane web components
import { SelectXAxis } from "./select-x-axis";
import { SelectYAxis } from "./select-y-axis";

type Props = {
  control: Control<IAnalyticsParams, unknown>;
  setValue: UseFormSetValue<IAnalyticsParams>;
  params: IAnalyticsParams;
  workspaceSlug: string;
  classNames?: string;
  isEpic?: boolean;
};

export const AnalyticsSelectParams = observer(function AnalyticsSelectParams(props: Props) {
  const { control, params, classNames, isEpic } = props;
  const { t } = useTranslation();
  const localizeOption = (option: { value: string; label: string }) =>
    t(`workspace_analytics.work_item_charts.axes.${option.value}`);
  const xAxisOptions = useMemo(
    () => ANALYTICS_X_AXIS_VALUES.filter((option) => option.value !== params.group_by),
    [params.group_by]
  );
  const groupByOptions = useMemo(
    () => ANALYTICS_X_AXIS_VALUES.filter((option) => option.value !== params.x_axis),
    [params.x_axis]
  );

  return (
    <div className={cn("flex w-full justify-between", classNames)}>
      <div className={`flex items-center gap-2`}>
        <Controller
          name="y_axis"
          control={control}
          render={({ field: { value, onChange } }) => (
            <SelectYAxis
              value={value}
              onChange={(val: ChartYAxisMetric | null) => {
                onChange(val);
              }}
              options={ANALYTICS_Y_AXIS_VALUES.map((option) => ({
                value: option.value,
                label: localizeOption(option),
              }))}
              hiddenOptions={[
                ChartYAxisMetric.ESTIMATE_POINT_COUNT,
                isEpic ? ChartYAxisMetric.WORK_ITEM_COUNT : ChartYAxisMetric.EPIC_WORK_ITEM_COUNT,
              ]}
            />
          )}
        />
        <Controller
          name="x_axis"
          control={control}
          render={({ field: { value, onChange } }) => (
            <SelectXAxis
              value={value}
              onChange={(val) => {
                onChange(val);
              }}
              label={
                <div className="flex items-center gap-2">
                  <CalendarOutline className="h-3 w-3" />
                  <span className={cn("text-secondary", value && "text-primary")}>
                    {value
                      ? t(`workspace_analytics.work_item_charts.axes.${value}`)
                      : t("workspace_analytics.work_item_charts.add_property")}
                  </span>
                </div>
              }
              options={xAxisOptions.map((option) => ({ value: option.value, label: localizeOption(option) }))}
            />
          )}
        />
        <Controller
          name="group_by"
          control={control}
          render={({ field: { value, onChange } }) => (
            <SelectXAxis
              value={value}
              onChange={(val) => {
                onChange(val);
              }}
              label={
                <div className="flex items-center gap-2">
                  <PreferencesOutline className="h-3 w-3" />
                  <span className={cn("text-secondary", value && "text-primary")}>
                    {value ? t(`workspace_analytics.work_item_charts.axes.${value}`) : t("common.group_by")}
                  </span>
                </div>
              }
              options={groupByOptions.map((option) => ({ value: option.value, label: localizeOption(option) }))}
              placeholder={t("common.group_by")}
              allowNoValue
            />
          )}
        />
      </div>
    </div>
  );
});
