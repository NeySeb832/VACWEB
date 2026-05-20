"""
Helpers de envio de correos del modulo authz.

Centraliza el render de templates HTML+texto y el envio multipart para que
las vistas (invite_create, password reset, etc.) no dupliquen el codigo.

Politica:
  - Siempre se envia version texto + version HTML (multipart/alternative).
  - El backend SMTP se configura via variables de entorno (settings_render.py).
  - En desarrollo local el backend es 'console' por defecto: los correos se
    imprimen en stdout en vez de enviarse.
  - Todas las funciones son fail-safe (no bloquean la vista si falla el envio).
"""
import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

logger = logging.getLogger(__name__)


def _send_branded_email(
    *,
    subject: str,
    to: list[str],
    template_base: str,
    context: dict,
    fail_silently: bool = True,
) -> bool:
    """
    Envia un correo multipart leyendo dos templates:
      - templates/{template_base}.txt  (version texto)
      - templates/{template_base}.html (version HTML)

    Devuelve True si Django acepto el envio, False si fallo.
    """
    try:
        text_body = render_to_string(f"{template_base}.txt", context)
        html_body = render_to_string(f"{template_base}.html", context)
    except Exception as exc:
        logger.error("No se pudo renderizar el correo %s: %s", template_base, exc)
        if not fail_silently:
            raise
        return False

    msg = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=to,
    )
    msg.attach_alternative(html_body, "text/html")

    try:
        sent = msg.send(fail_silently=fail_silently)
        return bool(sent)
    except Exception as exc:
        logger.error("Error enviando correo a %s: %s", to, exc)
        if not fail_silently:
            raise
        return False


# ─── API publica para las vistas ─────────────────────────────────────────────

def send_invitation_email(*, user, activate_url: str, expiry_hours: int) -> bool:
    """Envia el correo de invitacion / activacion de cuenta (CU-001, RN-9)."""
    if not user.email:
        logger.warning("Usuario %s no tiene email; no se envia invitacion.", user.username)
        return False

    context = {
        "user": user,
        "full_name": user.get_full_name() or user.username,
        "activate_url": activate_url,
        "expiry_hours": expiry_hours,
        "site_name": "VACWEB — Control Ganadero",
    }
    return _send_branded_email(
        subject="VACWEB — Activa tu cuenta",
        to=[user.email],
        template_base="email/invitation",
        context=context,
    )
