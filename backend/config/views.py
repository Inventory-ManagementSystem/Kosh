from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

class HealthAPIView(APIView):

    def get(self, request):
        return Response(
            {
                "status": "success",
                "message": "Kosh backend is running"
            },
            status=status.HTTP_200_OK
        )
    