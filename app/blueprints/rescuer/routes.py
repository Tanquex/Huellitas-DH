"""rescuer/routes.py — Panel exclusivo para rescatistas verificados."""
from flask import Blueprint, render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user
from app.models import (db, Pet, AdoptionRequest, Sighting, PetStatusLog,
                        AdoptionStatus, PetStatus, Donation, NotifType)
from app.utils import rescuer_required, create_notification, DOLORES_ZONES
from sqlalchemy import func
from app.utils import jwt_required

rescuer_bp = Blueprint("rescuer", __name__)


def _check_rescuer():
    if not current_user.is_authenticated or not current_user.is_rescuer:
        abort(403)


@rescuer_bp.route("/")
@jwt_required
@rescuer_required
def dashboard():
    """Dashboard principal del rescatista con métricas relevantes."""
    # Mascotas que el rescatista reportó o está gestionando
    my_pets = Pet.query.filter(
        (Pet.reporter_id == current_user.id) | (Pet.rescuer_id == current_user.id),
        Pet.is_active == True
    ).order_by(Pet.updated_at.desc()).all()

    # Solicitudes pendientes de revisión en sus mascotas
    my_pet_ids = [p.id for p in my_pets]
    pending_requests = AdoptionRequest.query.filter(
        AdoptionRequest.pet_id.in_(my_pet_ids),
        AdoptionRequest.status == AdoptionStatus.PENDING
    ).order_by(AdoptionRequest.created_at.desc()).all() if my_pet_ids else []

    # Avistamientos recientes de sus mascotas perdidas
    recent_sightings = Sighting.query.filter(
        Sighting.pet_id.in_(my_pet_ids),
        Sighting.is_confirmed == False
    ).order_by(Sighting.created_at.desc()).limit(10).all() if my_pet_ids else []

    stats = {
        "total":    len(my_pets),
        "lost":     sum(1 for p in my_pets if p.status == PetStatus.LOST),
        "urgent":   sum(1 for p in my_pets if p.status == PetStatus.URGENT),
        "adoption": sum(1 for p in my_pets if p.status == PetStatus.ADOPTION),
        "adopted":  sum(1 for p in my_pets if p.status == PetStatus.ADOPTED),
        "pending_requests": len(pending_requests),
        "sightings": len(recent_sightings),
    }
    return render_template("rescuer/dashboard.html",
                           my_pets=my_pets[:6], stats=stats,
                           pending_requests=pending_requests[:5],
                           recent_sightings=recent_sightings,
                           title="Panel Rescatista")


@rescuer_bp.route("/mis-mascotas")
@jwt_required
@rescuer_required
def my_pets():
    """Lista completa de mascotas gestionadas por el rescatista."""
    status = request.args.get("status", "")
    query  = Pet.query.filter(
        (Pet.reporter_id == current_user.id) | (Pet.rescuer_id == current_user.id),
        Pet.is_active == True
    )
    if status:
        query = query.filter_by(status=status)
    pets = query.order_by(Pet.updated_at.desc()).all()
    return render_template("rescuer/my_pets.html", pets=pets,
                           statuses=PetStatus.ALL, current_status=status,
                           title="Mis mascotas")


@rescuer_bp.route("/solicitudes")
@jwt_required
@rescuer_required
def all_requests():
    """Todas las solicitudes de adopción de mascotas del rescatista."""
    status_filter = request.args.get("status", "")
    page = request.args.get("page", 1, type=int)

    my_pet_ids = [p.id for p in Pet.query.filter(
        (Pet.reporter_id == current_user.id) | (Pet.rescuer_id == current_user.id),
        Pet.is_active == True
    ).with_entities(Pet.id).all()]

    query = AdoptionRequest.query.filter(
        AdoptionRequest.pet_id.in_(my_pet_ids)
    ) if my_pet_ids else AdoptionRequest.query.filter_by(id=0)

    if status_filter:
        query = query.filter_by(status=status_filter)

    requests = query.order_by(AdoptionRequest.created_at.desc()).paginate(page=page, per_page=15)
    return render_template("rescuer/requests.html",
                           requests=requests, status_filter=status_filter,
                           statuses=AdoptionStatus.ALL,
                           title="Solicitudes de adopción")


@rescuer_bp.route("/avistamientos")
@jwt_required
@rescuer_required
def sightings():
    """Avistamientos de mascotas perdidas gestionadas por el rescatista."""
    my_pet_ids = [p.id for p in Pet.query.filter(
        (Pet.reporter_id == current_user.id) | (Pet.rescuer_id == current_user.id),
        Pet.is_active == True,
        Pet.status.in_([PetStatus.LOST, PetStatus.URGENT])
    ).with_entities(Pet.id).all()]

    all_sightings = Sighting.query.filter(
        Sighting.pet_id.in_(my_pet_ids)
    ).order_by(Sighting.seen_at.desc()).all() if my_pet_ids else []

    return render_template("rescuer/sightings.html",
                           sightings=all_sightings, title="Avistamientos")


@rescuer_bp.route("/avistamiento/<int:sighting_id>/confirmar", methods=["POST"])
@jwt_required
@rescuer_required
def confirm_sighting(sighting_id):
    s = Sighting.query.get_or_404(sighting_id)
    my_ids = [p.id for p in Pet.query.filter(
        (Pet.reporter_id == current_user.id) | (Pet.rescuer_id == current_user.id)
    ).with_entities(Pet.id).all()]
    if s.pet_id not in my_ids:
        abort(403)
    s.is_confirmed = True
    db.session.commit()
    flash("Avistamiento confirmado.", "success")
    return redirect(url_for("rescuer.sightings"))


@rescuer_bp.route("/tomar-mascota/<int:pet_id>", methods=["POST"])
@jwt_required
@rescuer_required
def take_pet(pet_id):
    """Un rescatista puede asignarse como responsable de una mascota."""
    pet = Pet.query.get_or_404(pet_id)
    if pet.rescuer_id:
        flash("Esta mascota ya tiene un rescatista asignado.", "warning")
    else:
        pet.rescuer_id = current_user.id
        # Notificar al reportante
        if pet.reporter_id != current_user.id:
            create_notification(
                pet.reporter_id, NotifType.STATUS_CHANGE,
                "Rescatista asignado",
                f"{current_user.full_name} se asignó como rescatista de '{pet.display_name}'.",
                url_for("pets.detail", pet_id=pet.id)
            )
        db.session.commit()
        flash(f"Ahora eres el rescatista responsable de '{pet.display_name}'.", "success")
    return redirect(url_for("pets.detail", pet_id=pet.id))


@rescuer_bp.route("/notificaciones")
@jwt_required
def notifications():
    """Centro de notificaciones del usuario."""
    notifs = current_user.notifications.order_by(
        db.text("created_at DESC")
    ).paginate(page=request.args.get("page", 1, type=int), per_page=20)
    # Marcar todas como leídas
    current_user.notifications.filter_by(is_read=False).update({"is_read": True})
    db.session.commit()
    return render_template("rescuer/notifications.html", notifs=notifs, title="Notificaciones")


@rescuer_bp.route("/notificaciones/marcar-leidas", methods=["POST"])
@jwt_required
def mark_all_read():
    current_user.notifications.filter_by(is_read=False).update({"is_read": True})
    db.session.commit()
    return redirect(url_for("rescuer.notifications"))
