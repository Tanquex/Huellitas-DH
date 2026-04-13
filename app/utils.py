"""utils.py — helpers, decoradores de roles, notificaciones, zonas."""
import os, uuid
from functools import wraps
from flask import abort, current_app, url_for
from flask_login import current_user
from werkzeug.utils import secure_filename
from PIL import Image


ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}

DOLORES_ZONES = [
    "Centro Histórico", "Col. Hidalgo", "Col. Revolución", "Col. San Marcos",
    "Col. Las Palomas", "Col. El Mezquite", "Col. Nueva", "Fracc. Las Fuentes",
    "Fracc. Los Naranjos", "Ejido Santa Rosa", "Carretera a Guanajuato",
    "Carretera a San Diego", "Otra zona / Rancho",
]

STATUS_COLOR = {
    "Perdido":     ("bg-red-100 text-red-700",     "bg-red-500"),
    "Urgente":     ("bg-orange-100 text-orange-700","bg-orange-500"),
    "En Adopción": ("bg-blue-100 text-blue-700",   "bg-blue-500"),
    "Encontrado":  ("bg-green-100 text-green-700", "bg-green-500"),
    "Adoptado":    ("bg-purple-100 text-purple-700","bg-purple-500"),
}


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def save_pet_image(file) -> bytes | None:
    if not file or not allowed_file(file.filename):
        return None
    
    img = Image.open(file)
    img.thumbnail((900, 900), Image.LANCZOS)
    
    # Convert RGBA to RGB for JPEGs
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")
    
    # Save to bytes buffer
    from io import BytesIO
    buffer = BytesIO()
    img.save(buffer, format='JPEG', optimize=True, quality=85)
    return buffer.getvalue()


# No longer needed for binary storage


# ─── Decoradores de roles ────────────────────────────────────────────────────

def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not current_user.is_authenticated:
                abort(401)
            if current_user.role not in roles:
                abort(403)
            return f(*args, **kwargs)
        return decorated
    return decorator


def admin_required(f):
    return role_required("admin")(f)


def rescuer_required(f):
    return role_required("rescatista", "admin")(f)


# ─── Notificaciones ──────────────────────────────────────────────────────────

def create_notification(user_id: int, notif_type: str, title: str,
                        message: str, link: str = None):
    """Crea una notificación in-app para un usuario."""
    from app.models import db, Notification
    n = Notification(user_id=user_id, type=notif_type,
                     title=title, message=message, link=link)
    db.session.add(n)
    # No hacemos commit aquí para que el llamador lo controle
