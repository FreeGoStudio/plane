# 日期显示与用户偏好

需求来源：用户要求其他页面的日期汉化，并统一使用偏好设置中的“日期格式”；提议建立通用方法供各处调用。

## 使用方式

React 页面或组件使用 `@plane/utils` 导出的 `useDateFormatter()`：

```tsx
const { renderFormattedDate, renderFormattedTime } = useDateFormatter();
const dateLabel = renderFormattedDate(item.created_at);
const timeLabel = renderFormattedTime(item.created_at);
```

非 React 工具函数接收调用方传入的 `DateFormatter`，或显式调用 `createDateFormatter({ locale, order, timeZone })`。不要在模块级缓存某个用户的格式化实例。

静态配置中的 React 日期节点可使用 `<DateDisplay value={value} />`，它会订阅当前显示偏好。

`UserDateDisplayProvider` 将当前账户语言、时区和 `theme.homeDateOrder` 传给 `DateDisplayProvider`。沿用旧存储键，已保存的设置无需迁移。Provider 按账户上下文隔离；修改偏好会更新消费者，无需重载或清空编辑状态。`useMemo` / `useCallback` 中使用的格式化函数需加入依赖列表。

## 格式与边界

- `locale`：跟随界面语言，简体中文完整日期如 `2026年11月12日`。
- `ymd` / `mdy` / `dmy`：分别显示 `2026/11/12`、`11/12/2026`、`12/11/2026`。
- 旧显示 token 指定显示哪些字段（年、月、日、星期、时间），排列顺序由偏好控制。月份/年份标签无需补上日期字段。
- 日期字符串 `YYYY-MM-DD` 是日历日期，不因账户时区而变成前一天或后一天。
- 带时区的时间戳按账户时区显示；日期和时间使用同一时区。
- 日历选择器的本地 `Date` 用 `formatCalendarDate` 显示，保留用户选择的日历日期。
- 相对时间不套用年月日排列；中文使用中文时间单位。
- 缺失或无效日期保留空显示，由调用方决定占位符。

## 覆盖范围

首页、成员、工作项属性/列表/详情/活动、周期、模块、甘特图、日历、筛选摘要、评论、通知、页面历史、个人资料、项目设置、API 令牌及 Webhook 日期、分析图表。共享 `DateSelect` / `DateRangeSelect` 在 Provider 内统一使用偏好和中文日历；其他应用没有 Provider 时保留原有默认行为。

## 不用于数据格式

接口传值、日期比较、排序、分组键、日历导航、筛选存储继续使用原始日期或 `renderFormattedPayloadDate`。不要将本地化后的显示文本重新解析为日期。甘特图布局和日期计算不依赖翻译后的标签。

## 验证

`packages/blocks/src/property-select/date-display.test.tsx` 覆盖四种排列、局部日期字段、范围、跨时区时间戳、日期选择不漂移、API 格式保持、偏好切换即时渲染和多个 Provider 隔离。日期选择器既有交互测试继续验证选择行为。首页和成员测试继续验证之前的验收点。
