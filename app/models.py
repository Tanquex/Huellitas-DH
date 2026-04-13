"""
models.py — Huellitas Unidas DH
Modelos SQLAlchemy con todos los nuevos modelos añadidos:
  Sighting   — Avistamientos de mascotas perdidas
  Notification — Notificaciones in-app
"""
from datetime import datetime, timezone
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from flask_bcrypt import Bcrypt
import urllib.parse

db = SQLAlchemy()
bcrypt = Bcrypt()


# ─── Constantes de dominio ───────────────────────────────────────────────────

class UserRole:
    GENERAL  = "general"
    RESCUER  = "rescatista"
    ADMIN    = "admin"
    ALL      = [GENERAL, RESCUER, ADMIN]


class PetStatus:
    LOST     = "Perdido"
    ADOPTION = "En Adopción"
    URGENT   = "Urgente"
    FOUND    = "Encontrado"
    ADOPTED  = "Adoptado"
    ALL      = ["Perdido", "En Adopción", "Urgente", "Encontrado", "Adoptado"]
    INCOMPATIBLE = {
        "Perdido":     ["En Adopción", "Adoptado"],
        "En Adopción": ["Perdido", "Encontrado"],
        "Urgente":     ["Adoptado"],
    }


class PetSpecies:
    DOG   = "Perro"
    CAT   = "Gato"
    OTHER = "Otro"
    ALL   = ["Perro", "Gato", "Otro"]


class AdoptionStatus:
    PENDING  = "Pendiente"
    APPROVED = "Aprobado"
    REJECTED = "Rechazado"
    ALL      = ["Pendiente", "Aprobado", "Rechazado"]


class NotifType:
    COMMENT          = "comment"
    ADOPTION_REQUEST = "adoption_request"
    ADOPTION_RESULT  = "adoption_result"
    SIGHTING         = "sighting"
    STATUS_CHANGE    = "status_change"
    SYSTEM           = "system"


# ─── User ────────────────────────────────────────────────────────────────────

class User(db.Model, UserMixin):
    __tablename__ = "users"

    id               = db.Column(db.Integer, primary_key=True)
    username         = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email            = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash    = db.Column(db.String(256), nullable=False)
    full_name        = db.Column(db.String(150), nullable=False)
    phone_whatsapp   = db.Column(db.String(20), nullable=True)
    role             = db.Column(db.String(20), default=UserRole.GENERAL, nullable=False)
    is_active        = db.Column(db.Boolean, default=True, nullable=False)
    is_verified      = db.Column(db.Boolean, default=False, nullable=False)
    bio              = db.Column(db.Text, nullable=True)
    created_at       = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at       = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                                 onupdate=lambda: datetime.now(timezone.utc))

    # Relaciones
    reported_pets      = db.relationship("Pet", foreign_keys="Pet.reporter_id",
                                         backref="reporter", lazy="dynamic")
    rescuing_pets      = db.relationship("Pet", foreign_keys="Pet.rescuer_id",
                                         backref="rescuer", lazy="dynamic")
    comments           = db.relationship("Comment", backref="author", lazy="dynamic",
                                         cascade="all, delete-orphan")
    adoption_requests  = db.relationship("AdoptionRequest", backref="applicant",
                                         lazy="dynamic", cascade="all, delete-orphan")
    donations          = db.relationship("Donation", backref="donor", lazy="dynamic")
    notifications      = db.relationship("Notification", backref="recipient",
                                         lazy="dynamic", cascade="all, delete-orphan",
                                         foreign_keys="Notification.user_id")
    sightings          = db.relationship("Sighting", backref="reporter_user",
                                         lazy="dynamic", foreign_keys="Sighting.reporter_id")

    def set_password(self, password: str):
        self.password_hash = bcrypt.generate_password_hash(password).decode("utf-8")

    def check_password(self, password: str) -> bool:
        return bcrypt.check_password_hash(self.password_hash, password)

    @property
    def is_admin(self):
        return self.role == UserRole.ADMIN

    @property
    def is_rescuer(self):
        return self.role in (UserRole.RESCUER, UserRole.ADMIN)

    @property
    def unread_notifications_count(self):
        return self.notifications.filter_by(is_read=False).count()

    @property
    def initials(self):
        parts = self.full_name.split()
        if len(parts) >= 2:
            return f"{parts[0][0]}{parts[-1][0]}".upper()
        return self.full_name[0].upper()

    def __repr__(self):
        return f"<User {self.username} [{self.role}]>"


# ─── Pet ─────────────────────────────────────────────────────────────────────

class Pet(db.Model):
    __tablename__ = "pets"

    id                 = db.Column(db.Integer, primary_key=True)
    name               = db.Column(db.String(100), nullable=True)
    species            = db.Column(db.String(30), nullable=False)
    breed              = db.Column(db.String(100), nullable=True)
    approximate_age    = db.Column(db.String(50), nullable=True)
    color              = db.Column(db.String(100), nullable=False)
    description        = db.Column(db.Text, nullable=False)
    status             = db.Column(db.String(30), nullable=False, default=PetStatus.LOST, index=True)
    location_zone      = db.Column(db.String(200), nullable=False, index=True)
    location_reference = db.Column(db.String(255), nullable=True)
    last_seen_date     = db.Column(db.Date, nullable=True)
    image_data         = db.Column(db.LargeBinary, nullable=True)
    is_active          = db.Column(db.Boolean, default=True, nullable=False, index=True)
    reporter_id        = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    rescuer_id         = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at         = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at         = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                                   onupdate=lambda: datetime.now(timezone.utc))

    # Relaciones
    comments          = db.relationship("Comment", backref="pet", lazy="dynamic",
                                        cascade="all, delete-orphan")
    adoption_requests = db.relationship("AdoptionRequest", backref="pet", lazy="dynamic",
                                        cascade="all, delete-orphan")
    donations         = db.relationship("Donation", backref="pet", lazy="dynamic")
    status_logs       = db.relationship("PetStatusLog", backref="pet", lazy="dynamic",
                                        cascade="all, delete-orphan")
    sightings         = db.relationship("Sighting", backref="pet", lazy="dynamic",
                                        cascade="all, delete-orphan")

    def can_set_status(self, new_status: str) -> tuple:
        incompatible = PetStatus.INCOMPATIBLE.get(new_status, [])
        if self.status in incompatible:
            return False, f"No se puede cambiar de '{self.status}' a '{new_status}' directamente."
        return True, ""

    @property
    def whatsapp_url(self):
        if self.reporter and self.reporter.phone_whatsapp:
            phone = "".join(c for c in self.reporter.phone_whatsapp if c.isdigit())
            msg = f"Hola, vi la publicación de '{self.name or 'una mascota'}' en Huellitas Unidas DH."
            return f"https://wa.me/{phone}?text={urllib.parse.quote(msg)}"
        return None

    @property
    def pending_requests_count(self):
        return self.adoption_requests.filter_by(status=AdoptionStatus.PENDING).count()

    @property
    def display_name(self):
        return self.name or "Sin nombre"

    @property
    def species_emoji(self):
        return {"Perro": "🐕", "Gato": "🐈"}.get(self.species, "🐾")

    def __repr__(self):
        return f"<Pet {self.display_name} [{self.status}]>"


# ─── Comment ─────────────────────────────────────────────────────────────────

class Comment(db.Model):
    __tablename__ = "comments"

    id         = db.Column(db.Integer, primary_key=True)
    content    = db.Column(db.Text, nullable=False)
    pet_id     = db.Column(db.Integer, db.ForeignKey("pets.id"), nullable=False)
    author_id  = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    is_active  = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f"<Comment by user:{self.author_id} on pet:{self.pet_id}>"


# ─── AdoptionRequest ─────────────────────────────────────────────────────────

class AdoptionRequest(db.Model):
    __tablename__ = "adoption_requests"

    id                = db.Column(db.Integer, primary_key=True)
    pet_id            = db.Column(db.Integer, db.ForeignKey("pets.id"), nullable=False)
    applicant_id      = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    status            = db.Column(db.String(20), default=AdoptionStatus.PENDING, nullable=False, index=True)
    housing_type      = db.Column(db.String(50), nullable=False)
    has_yard          = db.Column(db.Boolean, default=False)
    home_size         = db.Column(db.String(50), nullable=True)
    has_children      = db.Column(db.Boolean, default=False)
    children_ages     = db.Column(db.String(100), nullable=True)
    has_other_pets    = db.Column(db.Boolean, default=False)
    other_pets_desc   = db.Column(db.String(255), nullable=True)
    previous_pets     = db.Column(db.Boolean, default=False)
    experience_desc   = db.Column(db.Text, nullable=True)
    reason            = db.Column(db.Text, nullable=False)
    aware_of_cost     = db.Column(db.Boolean, default=False)
    accepts_home_visit= db.Column(db.Boolean, default=False)
    contact_address   = db.Column(db.String(255), nullable=True)
    notes_rescuer     = db.Column(db.Text, nullable=True)
    created_at        = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at        = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                                  onupdate=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f"<AdoptionRequest pet:{self.pet_id} user:{self.applicant_id} [{self.status}]>"


# ─── Donation ────────────────────────────────────────────────────────────────

class Donation(db.Model):
    __tablename__ = "donations"

    id           = db.Column(db.Integer, primary_key=True)
    amount       = db.Column(db.Numeric(10, 2), nullable=False)
    description  = db.Column(db.String(255), nullable=True)
    pet_id       = db.Column(db.Integer, db.ForeignKey("pets.id"), nullable=True)
    donor_id     = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    is_anonymous = db.Column(db.Boolean, default=False)
    created_at   = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f"<Donation ${self.amount} pet:{self.pet_id}>"


# ─── PetStatusLog ────────────────────────────────────────────────────────────

class PetStatusLog(db.Model):
    __tablename__ = "pet_status_logs"

    id         = db.Column(db.Integer, primary_key=True)
    pet_id     = db.Column(db.Integer, db.ForeignKey("pets.id"), nullable=False)
    old_status = db.Column(db.String(30), nullable=True)
    new_status = db.Column(db.String(30), nullable=False)
    changed_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    note       = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    changer = db.relationship("User", foreign_keys=[changed_by])

    def __repr__(self):
        return f"<StatusLog pet:{self.pet_id} {self.old_status}→{self.new_status}>"


# ─── Sighting (NUEVO) ─────────────────────────────────────────────────────────
# Permite a ciudadanos reportar avistamientos de una mascota perdida,
# incluyendo zona y descripción, para ayudar a localizarla.

class Sighting(db.Model):
    __tablename__ = "sightings"

    id          = db.Column(db.Integer, primary_key=True)
    pet_id      = db.Column(db.Integer, db.ForeignKey("pets.id"), nullable=False)
    reporter_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    zone        = db.Column(db.String(200), nullable=False)
    reference   = db.Column(db.String(255), nullable=True)
    description = db.Column(db.Text, nullable=False)
    seen_at     = db.Column(db.DateTime, nullable=False,
                            default=lambda: datetime.now(timezone.utc))
    is_confirmed = db.Column(db.Boolean, default=False)  # confirmado por dueño/rescatista
    created_at  = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f"<Sighting pet:{self.pet_id} zone:{self.zone}>"


# ─── Notification (NUEVO) ────────────────────────────────────────────────────
# Notificaciones in-app para mantener a los usuarios informados:
# nuevo comentario, solicitud de adopción, resultado de solicitud, etc.

class Notification(db.Model):
    __tablename__ = "notifications"

    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    type       = db.Column(db.String(30), nullable=False)   # NotifType constant
    title      = db.Column(db.String(120), nullable=False)
    message    = db.Column(db.String(300), nullable=False)
    link       = db.Column(db.String(255), nullable=True)   # URL relativa destino
    is_read    = db.Column(db.Boolean, default=False, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f"<Notification user:{self.user_id} [{self.type}] read:{self.is_read}>"

class UserQuiz(db.Model):
    __tablename__ = "user_quizzes"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    
    # Respuestas (puedes guardarlas como JSON o texto largo)
    answers_json = db.Column(db.JSON, nullable=False)
    
    # Análisis de la IA
    ai_score = db.Column(db.Integer)  # 0 a 100
    ai_feedback = db.Column(db.Text)  # Explicación de la IA
    
    status = db.Column(db.String(20), default="Pendiente") # Pendiente, Revisado
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    user = db.relationship("User", backref=db.backref("quiz", uselist=False))