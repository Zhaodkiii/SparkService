import type { InjectionKey } from 'vue';

export type UpdateTabTitle = (path: string, title: string) => void;

export const updateTabTitleKey: InjectionKey<UpdateTabTitle> = Symbol('updateTabTitle');
