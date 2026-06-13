const GENDER_LABELS: Record<string, string> = {
  male: '男',
  female: '女',
  unknown: '未知',
};

export function formatGender(value?: string | null): string {
  const key = (value || 'unknown').trim().toLowerCase();
  return GENDER_LABELS[key] ?? '未知';
}

export function displayGender(record: { gender_label?: string; gender?: string | null }): string {
  return record.gender_label || formatGender(record.gender);
}
