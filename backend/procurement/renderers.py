import json
from rest_framework.renderers import BaseRenderer


class PDFRenderer(BaseRenderer):
  media_type = "application/pdf"
  format = "pdf"
  charset = None
  render_style = "binary"

  def render(self, data, accepted_media_type=None, renderer_context=None):
    if isinstance(data, bytes):
      return data
    return json.dumps(data).encode()
