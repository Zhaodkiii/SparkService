import { onMounted, onUnmounted } from 'vue';

export interface DocumentMetaInput {
  title?: string;
  description?: string;
  image?: string;
  url?: string;
  publishedAt?: string | null;
}

function upsertMeta(attr: 'name' | 'property', key: string, content: string) {
  if (!content) return;
  let el = document.querySelector(`meta[${attr}="${key}"]`) as HTMLMetaElement | null;
  if (!el) {
    el = document.createElement('meta');
    el.setAttribute(attr, key);
    document.head.appendChild(el);
  }
  el.content = content;
}

export function useDocumentMeta() {
  function updateMeta(input: DocumentMetaInput) {
    const title = input.title?.trim();
    const description = input.description?.trim();

    if (title) {
      document.title = title;
    }
    if (description) {
      upsertMeta('name', 'description', description);
    }
    if (title) {
      upsertMeta('property', 'og:title', title);
      upsertMeta('name', 'twitter:title', title);
    }
    if (description) {
      upsertMeta('property', 'og:description', description);
      upsertMeta('name', 'twitter:description', description);
    }
    if (input.image) {
      upsertMeta('property', 'og:image', input.image);
      upsertMeta('name', 'twitter:image', input.image);
      upsertMeta('name', 'twitter:card', 'summary_large_image');
    } else {
      upsertMeta('name', 'twitter:card', 'summary');
    }
    const url = input.url || (typeof window !== 'undefined' ? window.location.href : '');
    if (url) {
      upsertMeta('property', 'og:url', url);
    }
    upsertMeta('property', 'og:type', 'article');
    if (input.publishedAt) {
      upsertMeta('property', 'article:published_time', input.publishedAt);
    }
  }

  function resetMeta() {
    document.title = '小鲸健康';
    upsertMeta('name', 'description', '小鲸健康 - 健康科普内容');
  }

  onMounted(() => {
    if (!document.querySelector('meta[name="description"]')) {
      resetMeta();
    }
  });

  onUnmounted(() => {
    resetMeta();
  });

  return { updateMeta, resetMeta };
}
