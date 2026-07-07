<script setup lang="ts">
import { computed } from 'vue';
import MarkdownIt from 'markdown-it';
import DOMPurify from 'dompurify';

const props = defineProps<{ content: string }>();

const md = new MarkdownIt({
  html: false,
  linkify: true,
  breaks: true,
});

let hooksInstalled = false;

function ensureLinkHooks() {
  if (hooksInstalled || typeof window === 'undefined') return;
  DOMPurify.addHook('afterSanitizeAttributes', (node) => {
    if (node.tagName === 'A') {
      node.setAttribute('target', '_blank');
      node.setAttribute('rel', 'noopener noreferrer');
    }
  });
  hooksInstalled = true;
}

function wrapTables(html: string): string {
  return html.replace(/<table[\s\S]*?<\/table>/gi, (match) => {
    return `<div class="table-scroll">${match}</div>`;
  });
}

const html = computed(() => {
  ensureLinkHooks();
  const rendered = md.render(props.content || '');
  const sanitized = DOMPurify.sanitize(rendered, {
    USE_PROFILES: { html: true },
    ADD_ATTR: ['target', 'rel'],
  });
  return wrapTables(sanitized);
});
</script>

<template>
  <article class="markdown-content" v-html="html" />
</template>

<style src="../../../shared/styles/markdown-content.css"></style>
