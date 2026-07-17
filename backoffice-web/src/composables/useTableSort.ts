import { computed, reactive, type Ref } from 'vue';
import type { TableProps } from 'ant-design-vue';

export type SortOrder = 'asc' | 'desc';
export type AntSortOrder = 'ascend' | 'descend' | null;

export interface SortFieldConfig {
  key: string;
  apiField: string;
  defaultOrder?: SortOrder;
}

export interface UseTableSortOptions {
  defaultSortBy: string;
  defaultOrder?: SortOrder;
  fields: Record<string, SortFieldConfig>;
  onSortChange?: () => void;
}

function antOrderToApi(order: AntSortOrder | undefined): SortOrder | null {
  if (order === 'ascend') return 'asc';
  if (order === 'descend') return 'desc';
  return null;
}

function apiOrderToAnt(order: SortOrder): AntSortOrder {
  return order === 'asc' ? 'ascend' : 'descend';
}

/**
 * 后台表格统一排序：Ant Design Vue sorter <-> sort_by/order。
 * 页面只声明可排序字段和默认排序，不重复写转换逻辑。
 */
export function useTableSort(options: UseTableSortOptions) {
  const defaultOrder: SortOrder = options.defaultOrder ?? 'desc';
  const state = reactive({
    sortBy: options.defaultSortBy,
    order: defaultOrder,
  });

  const sortQuery: Ref<{ sort_by: string; order: SortOrder }> = computed(() => ({
    sort_by: state.sortBy,
    order: state.order,
  }));

  function getColumnSortOrder(columnKey: string): AntSortOrder {
    const field = options.fields[columnKey];
    if (!field || state.sortBy !== field.apiField) {
      return null;
    }
    return apiOrderToAnt(state.order);
  }

  function resetSort() {
    state.sortBy = options.defaultSortBy;
    state.order = defaultOrder;
  }

  const handleTableChange: TableProps['onChange'] = (_pagination, _filters, sorter) => {
    const single = Array.isArray(sorter) ? sorter[0] : sorter;
    const columnKey = String(single?.columnKey ?? single?.field ?? '');
    const field = options.fields[columnKey];
    const nextOrder = antOrderToApi(single?.order ?? null);

    if (!field || !nextOrder) {
      resetSort();
    } else {
      state.sortBy = field.apiField;
      state.order = nextOrder;
    }
    options.onSortChange?.();
  };

  return {
    sortState: state,
    sortQuery,
    getColumnSortOrder,
    handleTableChange,
    resetSort,
  };
}
