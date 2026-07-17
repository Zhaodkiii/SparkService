import type { Dayjs } from 'dayjs';

export type AdminRangeDateValue = Dayjs | string | null | undefined;

const ADMIN_DATETIME_FORMAT = 'YYYY-MM-DD HH:mm:ss';

/**
 * 将 a-range-picker 的变更值格式化为后台统一日期时间字符串。
 * 兼容 Dayjs 与 string（配置 value-format 时可能返回字符串）。
 */
export function formatAdminDateTimeRangeValue(value: AdminRangeDateValue): string {
  if (!value) {
    return '';
  }
  return typeof value === 'string' ? value : value.format(ADMIN_DATETIME_FORMAT);
}
