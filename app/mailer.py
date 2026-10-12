"""SMTP delivery; secrets are read only from environment variables."""
import os, ssl, smtplib
from email.message import EmailMessage
from fastapi import HTTPException

def send_email(recipient, subject, body):
    host=os.getenv("SMTP_HOST","smtp.ionos.de")
    port=int(os.getenv("SMTP_PORT","587"))
    username=os.getenv("SMTP_USER","noreply@agrosskopf.de")
    password=os.getenv("SMTP_PASSWORD","")
    sender=os.getenv("SMTP_FROM",username)
    if not password:
        raise HTTPException(503,"SMTP is not configured")
    message=EmailMessage()
    message["From"]=sender
    message["To"]=recipient
    message["Subject"]=subject
    message.set_content(body)
    try:
        if port==465:
            with smtplib.SMTP_SSL(host,port,timeout=15,context=ssl.create_default_context()) as client:
                client.login(username,password);client.send_message(message)
        else:
            with smtplib.SMTP(host,port,timeout=15) as client:
                client.ehlo();client.starttls(context=ssl.create_default_context())
                client.ehlo();client.login(username,password);client.send_message(message)
    except (OSError,smtplib.SMTPException) as exc:
        raise HTTPException(503,"Email delivery temporarily unavailable") from exc
