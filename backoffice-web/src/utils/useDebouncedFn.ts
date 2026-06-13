export function useDebouncedFn<T extends (...args: never[]) => void>(fn: T, delayMs = 400) {
  let timer: ReturnType<typeof setTimeout> | undefined;
  return (...args: Parameters<T>) => {
    if (timer) {
      clearTimeout(timer);
    }
    timer = setTimeout(() => fn(...args), delayMs);
  };
}
