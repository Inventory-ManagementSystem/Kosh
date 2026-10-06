from rest_framework.pagination import PageNumberPagination

from .responses import success_response


class StandardPagination(PageNumberPagination):
  page_size = 10
  page_size_query_param = "page_size"
  max_page_size = 50
  message = "List fetched."
  def get_paginated_response(self, data):
    return success_response(
      self.message,
      {
        "count": self.page.paginator.count,
        "next": self.get_next_link(),
        "previous": self.get_previous_link(),
        "results": data,
      },
    )
