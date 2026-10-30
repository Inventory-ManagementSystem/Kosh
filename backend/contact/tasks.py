import logging

from celery import shared_task
from django.conf import settings
from django.core.mail import EmailMessage

logger=logging.getLogger(__name__)

@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_contact_email(self, sender_email, message):
  if not settings.CONTACT_RECEIVER_EMAIL:
    logger.error("CONTACT_RECEIVER_EMAIL is not set; contact message from %s dropped", sender_email)
    return
  mail = EmailMessage(
    subject=f"[Kosh contact] Message from {sender_email}",
    body=f"From: {sender_email}\n\n{message}",
    from_email=settings.DEFAULT_FROM_EMAIL,
    to=[settings.CONTACT_RECEIVER_EMAIL],
    reply_to=[sender_email],
  )
  try:
    mail.send(fail_silently=False)
  except Exception as exc:
    logger.exception("Contact email from %s failed", sender_email)
    raise self.retry(exc=exc)
