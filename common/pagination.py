from rest_framework.pagination import CursorPagination, PageNumberPagination


class StandardResultsSetPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 100


class CreatedCursorPagination(CursorPagination):
    page_size = 10
    ordering = "-created_at"
