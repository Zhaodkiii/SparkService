import { isImeComposing, type KeyboardSubmitEventLike } from "@/lib/composer-keyboard";

export interface DoctorKeyboardEventLike extends KeyboardSubmitEventLike {
  metaKey?: boolean;
  ctrlKey?: boolean;
}

export function shouldSubmitDoctorMessage(event: DoctorKeyboardEventLike): boolean {
  return event.key === "Enter" && (event.metaKey === true || event.ctrlKey === true) && !isImeComposing(event);
}
