import { ref } from 'vue';
import { copyText } from '../utils/clipboard';

export function usePublicShare() {
  const toast = ref('');
  let toastTimer: ReturnType<typeof setTimeout> | null = null;

  function showToast(message: string) {
    toast.value = message;
    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(() => {
      toast.value = '';
    }, 2500);
  }

  async function shareOrCopy(options: { title: string; text?: string; url: string }) {
    const { title, text, url } = options;
    if (navigator.share) {
      try {
        await navigator.share({ title, text: text || title, url });
        return;
      } catch (err) {
        if (err instanceof DOMException && err.name === 'AbortError') {
          return;
        }
      }
    }
    const ok = await copyText(url);
    showToast(ok ? '链接已复制' : '复制失败，请手动复制链接');
  }

  const APP_STORE_URL = 'https://apps.apple.com/cn/app/id6751417431';

  function openApp(schemeUrl?: string) {
    if (!schemeUrl) {
      window.location.href = APP_STORE_URL;
      return;
    }
    // 尝试唤起 App；若 1.5s 内页面仍可见，说明 App 未安装，跳转 App Store
    const start = Date.now();
    window.location.href = schemeUrl;
    setTimeout(() => {
      if (document.hidden) return;
      if (Date.now() - start < 3000) {
        window.location.href = APP_STORE_URL;
      }
    }, 1500);
  }

  return { toast, shareOrCopy, openApp, showToast };
}
