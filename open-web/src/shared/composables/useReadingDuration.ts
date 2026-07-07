import { onMounted, onUnmounted } from 'vue';
import { recordPublicArticleDurationBeacon } from '../../modules/content/api/contentApi';

const MIN_DURATION_SECONDS = 5;

export function useReadingDuration(options: {
  articleId: () => number | null;
  locale: () => string;
  sessionId: string;
}) {
  let visibleAt = Date.now();
  let accumulated = 0;
  let flushed = false;

  function tickVisible() {
    if (document.visibilityState === 'visible') {
      accumulated += Math.floor((Date.now() - visibleAt) / 1000);
    }
  }

  function resume() {
    visibleAt = Date.now();
  }

  function flush() {
    if (flushed) return;
    tickVisible();
    const id = options.articleId();
    if (!id || accumulated < MIN_DURATION_SECONDS) return;

    const duration = accumulated;
    accumulated = 0;
    flushed = true;

    const payload = {
      locale: options.locale(),
      duration_seconds: duration,
      session_id: options.sessionId,
      client_platform: 'web' as const,
    };

    const sent = recordPublicArticleDurationBeacon(id, payload);
    if (!sent) {
      flushed = false;
      accumulated = duration;
    }
  }

  function onVisibilityChange() {
    if (document.visibilityState === 'hidden') {
      tickVisible();
      flush();
    } else {
      resume();
    }
  }

  function onPageHide() {
    tickVisible();
    flush();
  }

  onMounted(() => {
    resume();
    document.addEventListener('visibilitychange', onVisibilityChange);
    window.addEventListener('pagehide', onPageHide);
  });

  onUnmounted(() => {
    tickVisible();
    flush();
    document.removeEventListener('visibilitychange', onVisibilityChange);
    window.removeEventListener('pagehide', onPageHide);
  });

  return { flush };
}
