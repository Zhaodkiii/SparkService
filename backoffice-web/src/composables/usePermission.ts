import { computed } from 'vue';
import { useAuthStore } from '../stores/auth';

export function usePermission(code: string) {
  const auth = useAuthStore();
  return computed(() => auth.hasPermission(code));
}
