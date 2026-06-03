import dayjs from 'dayjs';

const DATETIME_FORMAT = 'YYYY-MM-DD HH:mm:ss';
const DATE_FORMAT = 'YYYY-MM-DD';

function toDayjs(value?: string | number | Date | null) {
  if (value === null || value === undefined || value === '') {
    return null;
  }

  if (value instanceof Date) {
    const parsed = dayjs(value);
    return parsed.isValid() ? parsed : null;
  }

  if (typeof value === 'number') {
    const ms = value >= 1e12 ? value : value * 1000;
    const parsed = dayjs(ms);
    return parsed.isValid() ? parsed : null;
  }

  const parsed = dayjs(value);
  return parsed.isValid() ? parsed : null;
}

export function formatDateTime(value?: string | number | Date | null): string {
  const parsed = toDayjs(value);
  return parsed ? parsed.format(DATETIME_FORMAT) : '-';
}

export function formatDate(value?: string | number | Date | null): string {
  const parsed = toDayjs(value);
  return parsed ? parsed.format(DATE_FORMAT) : '-';
}
