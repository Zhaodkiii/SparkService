from django.core.paginator import Paginator


def paginate_queryset(queryset, request, default_page_size: int = 20):
    try:
        page = max(int(request.query_params.get("page", "1")), 1)
    except ValueError:
        page = 1
    try:
        page_size = min(max(int(request.query_params.get("page_size", str(default_page_size))), 1), 100)
    except ValueError:
        page_size = default_page_size
    paginator = Paginator(queryset, page_size)
    page_obj = paginator.get_page(page)
    return page_obj, {
        "page": page_obj.number,
        "page_size": page_size,
        "total": paginator.count,
        "total_pages": paginator.num_pages,
    }
