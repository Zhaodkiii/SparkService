export const AI_PROMPT_KEYWORDS = {
  currentDate: '{{CURRENT_DATE}}',
} as const;

export const AIPromptKeywords = {
  currentDate: AI_PROMPT_KEYWORDS.currentDate,
  contains(keyword: string, text: string): boolean {
    return text.includes(keyword);
  },
  setting(keyword: string, enabled: boolean, text: string): string {
    const lines = text
      .split('\n')
      .map((line) => line.trim())
      .filter((line) => line !== keyword);
    if (enabled) {
      lines.push(keyword);
    }
    return lines.join('\n');
  },
} as const;
