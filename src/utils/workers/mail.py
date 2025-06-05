"""Email sending worker using SMTP"""
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import settings
from src.utils import worker

log = logging.getLogger(__name__)

@worker.register
def send_mail(
    subject: str,
    body: str,
    to_email: str,
):
    msg = MIMEMultipart()
    msg["From"] = settings.email.FROM
    msg["To"] = to_email
    msg["subject"] = subject
    msg.attach(MIMEText(body))
    log.info(f"Connecting to SMTP server: {settings.email.host}:{settings.email.port}")
    server = smtplib.SMTP(settings.email.host, settings.email.port)
    server.starttls()

    log.info("Logging in to SMTP server")
    server.login(settings.email.login, settings.email.password)

    text = msg.as_string()
    log.info(f"Sending email to {to_email}")
    server.sendmail(settings.email.FROM, to_email, text)

    server.quit()
    log.info("Email sent successfully")
