export function calcActionsColWidth(params: {
  /** 该列最多会出现多少个按钮（按权限/状态取最大值） */
  buttons: number;
  /** 最小宽度，默认 60 */
  min?: number;
  /** 单个按钮预留宽度（含文字），默认 80 */
  perButton?: number;
  /** 按钮间距，默认 8（与 TableHoverActions gap 一致） */
  gap?: number;
  /** 可选最大宽度 */
  max?: number;
}) {
  const min = params.min ?? 60;
  const per = params.perButton ?? 80;
  const gap = params.gap ?? 8;
  const count = Math.max(0, Math.floor(params.buttons));

  const raw = count <= 0 ? min : count * per + (count - 1) * gap;
  const clampedMin = Math.max(min, raw);
  if (typeof params.max === 'number') {
    return Math.min(params.max, clampedMin);
  }
  return clampedMin;
}

