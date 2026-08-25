export interface KeyboardSubmitEventLike { key: string; shiftKey?: boolean; isComposing?: boolean; keyCode?: number; }

export function isImeComposing(event: KeyboardSubmitEventLike): boolean {
  return event.isComposing === true || event.keyCode === 229;
}

export function shouldSubmitOnEnter(event: KeyboardSubmitEventLike): boolean {
  return event.key === "Enter" && !event.shiftKey && !isImeComposing(event);
}
