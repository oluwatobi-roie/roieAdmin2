"""SMTP transport; credentials and raw SMTP responses never leave this module."""
import os
import smtplib
import ssl
from email.headerregistry import Address
from email.message import EmailMessage
from email.utils import formatdate, parseaddr
from pathlib import Path

from dotenv import dotenv_values
from services.finance import FinanceError


def mailbox(value):
    if not isinstance(value, str) or any(char in value for char in "\r\n"):
        raise FinanceError("A valid customer email address is required.")
    try:
        address = Address(addr_spec=value.strip())
        if not address.username or not address.domain or "." not in address.domain:
            raise ValueError()
        # SMTPUTF8 is not assumed; international domains may use their ASCII form.
        address.addr_spec.encode("ascii")
        return address.addr_spec
    except (ValueError, UnicodeError) as exc:
        raise FinanceError("A valid customer email address is required.") from exc


def smtp_settings():
    # Local development may keep SMTP in the repo root and DB config in backend.
    # Environment variables take precedence. Never load root DB settings here.
    root = dotenv_values(Path(__file__).resolve().parents[2] / ".env", interpolate=False)
    def setting(key, default=""):
        return os.environ.get(key, root.get(key) or default)
    try:
        port = int(setting("SMTP_PORT", "587"))
        if not 1 <= port <= 65535:
            raise ValueError()
    except (TypeError, ValueError) as exc:
        raise FinanceError("SMTP_PORT must be a valid port number.", 503) from exc
    sender = setting("SMTP_FROM")
    tls = setting("SMTP_TLS", "true").lower()
    if tls not in ("true", "false"):
        raise FinanceError("SMTP_TLS must be true or false.", 503)
    if not setting("SMTP_HOST") or not sender:
        raise FinanceError("Email is not configured. Set SMTP_HOST and SMTP_FROM on the backend.", 503)
    if any(char in sender for char in "\r\n"):
        raise FinanceError("SMTP_FROM is invalid.", 503)
    try:
        envelope = mailbox(parseaddr(sender)[1])
    except FinanceError as exc:
        raise FinanceError("SMTP_FROM must contain a valid sender address.", 503) from exc
    user, password = setting("SMTP_USER"), setting("SMTP_PASSWORD")
    if bool(user) != bool(password):
        raise FinanceError("Set both SMTP_USER and SMTP_PASSWORD on the backend.", 503)
    if user and tls == "false" and port != 465:
        raise FinanceError("Enable SMTP_TLS before sending SMTP credentials.", 503)
    return dict(host=setting("SMTP_HOST"), port=port, user=user, password=password,
                sender=sender, envelope=envelope, tls=tls == "true")


def send_document(settings, operation, attachment):
    message = EmailMessage()
    message["From"] = settings["sender"]
    message["To"] = operation["recipient"]
    message["Subject"] = f"RoieTrackers | {operation['label']} {operation['document_number']}"
    message["Message-ID"] = operation["message_id"]
    message["Date"] = formatdate(localtime=False)
    message.set_content(f"Hello {operation['customer_name']},\n\nPlease find your {operation['label'].lower()} "
                        f"{operation['document_number']} attached as a PDF.\n\n"
                        "Thank you for choosing RoieTrackers.\nRoie Technologies Ltd")
    message.add_attachment(attachment, maintype="application", subtype="pdf", filename=operation["filename"])
    connection, sending = None, False
    try:
        context = ssl.create_default_context()
        if settings["port"] == 465:
            connection = smtplib.SMTP_SSL(settings["host"], settings["port"], timeout=10, context=context)
        else:
            connection = smtplib.SMTP(settings["host"], settings["port"], timeout=10)
            connection.ehlo()
            if settings["tls"]:
                connection.starttls(context=context)
                connection.ehlo()
        if settings["user"]:
            connection.login(settings["user"], settings["password"])
        sending = True
        refused = connection.send_message(message, from_addr=settings["envelope"], to_addrs=[operation["recipient"]])
        if refused:
            return "failed", "The mail server rejected the recipient. Check the customer's email address."
        return "sent", "Email sent."
    except smtplib.SMTPAuthenticationError:
        return "failed", "SMTP sign-in failed. Check the backend SMTP credentials or app password."
    except (smtplib.SMTPRecipientsRefused, smtplib.SMTPSenderRefused, smtplib.SMTPDataError):
        return "failed", "The mail server rejected this message. Check the sender and customer email settings."
    except (smtplib.SMTPException, OSError, ValueError):
        if sending:
            return "unknown", "Delivery could not be confirmed. Check the sender's mailbox before sending again to avoid a duplicate."
        return "failed", "Could not connect securely to the mail server. Check the SMTP settings and server connection."
    finally:
        if connection is not None:
            # Closing cannot turn a successful DATA acceptance into a failure.
            try:
                connection.close()
            except OSError:
                pass
