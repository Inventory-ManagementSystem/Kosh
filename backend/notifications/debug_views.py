import json
from django.shortcuts import render
from .views import firebase_web_config


def push_test_page(request):
  return render(request, "notifications/push_test.html")

def push_test_service_worker(request):
  return render(
    request,
    "notifications/push_sw.js",
    {"firebase_config": json.dumps(firebase_web_config())},
    content_type="application/javascript",
  )
