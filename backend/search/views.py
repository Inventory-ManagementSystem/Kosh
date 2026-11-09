from django.shortcuts import render

# Create your views here.

from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from accounts.permissions import HasBusinessAccess
from accounts.responses import success_response

from .SwaggerDocs import global_search_docs
from .services import global_search
from .throttles import SearchThrottle

@global_search_docs
class GlobalSearchApi(APIView):
  permission_classes = [IsAuthenticated, HasBusinessAccess]
  throttle_classes=[SearchThrottle]
  def get(self, request):
    data = global_search(request.business, request.query_params.get("q"))
    return success_response("Search results fetched.", data)
