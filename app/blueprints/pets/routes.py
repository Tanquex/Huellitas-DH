"""pets/routes.py — CRUD mascotas, comentarios, avistamientos, cambio de estado."""
from flask import Blueprint, render_template, redirect, url_for, flash, request, abort, Response, g
from app.utils import jwt_required
from app.models import (db, Pet, Comment, PetStatusLog, Sighting,
                        PetStatus, AdoptionRequest, NotifType)
from app.utils import save_pet_image, DOLORES_ZONES, create_notification
from .forms import PetForm, CommentForm, StatusUpdateForm, SightingForm

pets_bp = Blueprint("pets", __name__)
PER_PAGE = 12


@pets_bp.route("/")
def index():
    page    = request.args.get("page", 1, type=int)
    status  = request.args.get("status", "")
    zone    = request.args.get("zone", "")
    species = request.args.get("species", "")
    q       = request.args.get("q", "")

    query = Pet.query.filter_by(is_active=True)
    if status:  query = query.filter_by(status=status)
    if zone:    query = query.filter_by(location_zone=zone)
    if species: query = query.filter_by(species=species)
    if q:
        query = query.filter(
            Pet.description.ilike(f"%{q}%") |
            Pet.name.ilike(f"%{q}%") |
            Pet.color.ilike(f"%{q}%")
        )
    pets = query.order_by(Pet.created_at.desc()).paginate(page=page, per_page=PER_PAGE)
    return render_template("pets/index.html", pets=pets,
                           statuses=PetStatus.ALL, zones=DOLORES_ZONES,
                           title="Mascotas")


@pets_bp.route("/nueva", methods=["GET", "POST"])
@jwt_required
def create():
    form = PetForm()
    if form.validate_on_submit():
        img_data = save_pet_image(form.image.data) if form.image.data and form.image.data.filename else None
        pet = Pet(
            name=form.name.data or None, species=form.species.data,
            breed=form.breed.data or None, approximate_age=form.approximate_age.data or None,
            color=form.color.data, description=form.description.data,
            status=form.status.data, location_zone=form.location_zone.data,
            location_reference=form.location_reference.data or None,
            last_seen_date=form.last_seen_date.data, image_data=img_data,
            reporter_id=g.current_user.id,
        )
        db.session.add(pet)
        db.session.flush()
        db.session.add(PetStatusLog(pet_id=pet.id, old_status=None,
                                    new_status=pet.status, changed_by=g.current_user.id,
                                    note="Reporte inicial"))
        db.session.commit()
        flash("¡Mascota reportada exitosamente!", "success")
        return redirect(url_for("pets.detail", pet_id=pet.id))
    return render_template("pets/form.html", form=form, title="Reportar mascota", action="Crear")


@pets_bp.route("/<int:pet_id>")
def detail(pet_id):
    pet = Pet.query.get_or_404(pet_id)
    if not pet.is_active and not (g.current_user.is_authenticated and g.current_user.is_admin):
        abort(404)
    comment_form  = CommentForm()
    status_form   = StatusUpdateForm()
    sighting_form = SightingForm()
    comments  = pet.comments.filter_by(is_active=True).order_by(Comment.created_at.asc()).all()
    logs      = pet.status_logs.order_by(PetStatusLog.created_at.desc()).all()
    sightings = pet.sightings.order_by(Sighting.seen_at.desc()).all()
    user_request = None
    if g.current_user.is_authenticated:
        user_request = AdoptionRequest.query.filter_by(
            pet_id=pet_id, applicant_id=g.current_user.id).first()
    return render_template("pets/detail.html", pet=pet,
                           comment_form=comment_form, status_form=status_form,
                           sighting_form=sighting_form,
                           comments=comments, logs=logs, sightings=sightings,
                           user_request=user_request, title=pet.display_name)


@pets_bp.route("/<int:pet_id>/editar", methods=["GET", "POST"])
@jwt_required
def edit(pet_id):
    pet = Pet.query.get_or_404(pet_id)
    if pet.reporter_id != g.current_user.id and not g.current_user.is_rescuer:
        abort(403)
    form = PetForm(obj=pet)
    if form.validate_on_submit():
        old_status = pet.status
        if form.status.data != old_status:
            ok, msg = pet.can_set_status(form.status.data)
            if not ok:
                flash(msg, "danger")
                return render_template("pets/form.html", form=form, title="Editar", action="Editar", pet=pet)
        if form.image.data and form.image.data.filename:
            pet.image_data = save_pet_image(form.image.data)
        pet.name = form.name.data or None
        pet.species = form.species.data
        pet.breed = form.breed.data or None
        pet.approximate_age = form.approximate_age.data or None
        pet.color = form.color.data
        pet.description = form.description.data
        pet.location_zone = form.location_zone.data
        pet.location_reference = form.location_reference.data or None
        pet.last_seen_date = form.last_seen_date.data
        if form.status.data != old_status:
            pet.status = form.status.data
            db.session.add(PetStatusLog(pet_id=pet.id, old_status=old_status,
                                        new_status=pet.status, changed_by=g.current_user.id,
                                        note="Actualizado por editor"))
        db.session.commit()
        flash("Reporte actualizado.", "success")
        return redirect(url_for("pets.detail", pet_id=pet.id))
    return render_template("pets/form.html", form=form, title="Editar mascota", action="Editar", pet=pet)


@pets_bp.route("/<int:pet_id>/eliminar", methods=["POST"])
@jwt_required
def delete(pet_id):
    pet = Pet.query.get_or_404(pet_id)
    if pet.reporter_id != g.current_user.id and not g.current_user.is_admin:
        abort(403)
    pet.is_active = False
    db.session.commit()
    flash("Reporte eliminado.", "info")
    return redirect(url_for("pets.index"))


@pets_bp.route("/<int:pet_id>/comentar", methods=["POST"])
@jwt_required
def comment(pet_id):
    pet  = Pet.query.get_or_404(pet_id)
    form = CommentForm()
    if form.validate_on_submit():
        c = Comment(content=form.content.data, pet_id=pet.id, author_id=g.current_user.id)
        db.session.add(c)
        # Notificar al dueño del reporte
        if pet.reporter_id != g.current_user.id:
            create_notification(
                pet.reporter_id, NotifType.COMMENT,
                "Nuevo comentario",
                f"{g.current_user.full_name} comentó en '{pet.display_name}'.",
                url_for("pets.detail", pet_id=pet.id)
            )
        db.session.commit()
        flash("Comentario publicado.", "success")
    return redirect(url_for("pets.detail", pet_id=pet.id))


@pets_bp.route("/comentario/<int:comment_id>/eliminar", methods=["POST"])
@jwt_required
def delete_comment(comment_id):
    c = Comment.query.get_or_404(comment_id)
    if c.author_id != g.current_user.id and not g.current_user.is_admin:
        abort(403)
    pet_id = c.pet_id
    c.is_active = False
    db.session.commit()
    flash("Comentario eliminado.", "info")
    return redirect(url_for("pets.detail", pet_id=pet_id))


@pets_bp.route("/<int:pet_id>/estado", methods=["POST"])
@jwt_required
def update_status(pet_id):
    pet  = Pet.query.get_or_404(pet_id)
    if pet.reporter_id != g.current_user.id and not g.current_user.is_rescuer:
        abort(403)
    form = StatusUpdateForm()
    if form.validate_on_submit():
        ok, msg = pet.can_set_status(form.status.data)
        if not ok:
            flash(msg, "danger")
        else:
            old = pet.status
            pet.status = form.status.data
            db.session.add(PetStatusLog(pet_id=pet.id, old_status=old,
                                        new_status=pet.status, changed_by=g.current_user.id,
                                        note=form.note.data or None))
            db.session.commit()
            flash(f"Estado actualizado a '{pet.status}'.", "success")
    return redirect(url_for("pets.detail", pet_id=pet.id))


@pets_bp.route("/<int:pet_id>/avistamiento", methods=["POST"])
@jwt_required
def add_sighting(pet_id):
    pet  = Pet.query.get_or_404(pet_id)
    form = SightingForm()
    if form.validate_on_submit():
        s = Sighting(
            pet_id=pet.id, reporter_id=g.current_user.id,
            zone=form.zone.data, reference=form.reference.data or None,
            description=form.description.data, seen_at=form.seen_at.data,
        )
        db.session.add(s)
        # Notificar al dueño
        if pet.reporter_id != g.current_user.id:
            create_notification(
                pet.reporter_id, NotifType.SIGHTING,
                "Nuevo avistamiento",
                f"Alguien vio a '{pet.display_name}' en {form.zone.data}.",
                url_for("pets.detail", pet_id=pet.id)
            )
        db.session.commit()
        flash("¡Avistamiento reportado! El dueño ha sido notificado.", "success")
    return redirect(url_for("pets.detail", pet_id=pet.id))


@pets_bp.route("/<int:pet_id>/imagen")
def get_image(pet_id):
    pet = Pet.query.get_or_404(pet_id)
    if not pet.image_data:
        abort(404)
    return Response(pet.image_data, mimetype='image/jpeg')
