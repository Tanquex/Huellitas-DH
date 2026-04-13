"""adoptions/routes.py"""
from flask import Blueprint, render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user
from app.models import db, Pet, AdoptionRequest, AdoptionStatus, PetStatus, PetStatusLog, NotifType
from app.utils import rescuer_required, create_notification
from .forms import AdoptionRequestForm
from app.utils import jwt_required

adoptions_bp = Blueprint("adoptions", __name__)


@adoptions_bp.route("/solicitar/<int:pet_id>", methods=["GET", "POST"])
@jwt_required
def request_adoption(pet_id):
    pet = Pet.query.get_or_404(pet_id)
    if pet.status not in (PetStatus.ADOPTION, PetStatus.URGENT):
        flash("Esta mascota no está disponible para adopción.", "warning")
        return redirect(url_for("pets.detail", pet_id=pet.id))
    if AdoptionRequest.query.filter_by(pet_id=pet_id, applicant_id=current_user.id).first():
        flash("Ya enviaste una solicitud para esta mascota.", "info")
        return redirect(url_for("pets.detail", pet_id=pet.id))

    form = AdoptionRequestForm()
    if form.validate_on_submit():
        req = AdoptionRequest(
            pet_id=pet.id, applicant_id=current_user.id,
            housing_type=form.housing_type.data, home_size=form.home_size.data or None,
            has_yard=form.has_yard.data, has_children=form.has_children.data,
            children_ages=form.children_ages.data or None, has_other_pets=form.has_other_pets.data,
            other_pets_desc=form.other_pets_desc.data or None, previous_pets=form.previous_pets.data,
            experience_desc=form.experience_desc.data or None, reason=form.reason.data,
            aware_of_cost=form.aware_of_cost.data, accepts_home_visit=form.accepts_home_visit.data,
            contact_address=form.contact_address.data or None,
        )
        db.session.add(req)
        # Notificar al rescatista / reportante
        create_notification(
            pet.reporter_id, NotifType.ADOPTION_REQUEST,
            "Nueva solicitud de adopción",
            f"{current_user.full_name} quiere adoptar a '{pet.display_name}'.",
            url_for("adoptions.pet_requests", pet_id=pet.id)
        )
        db.session.commit()
        flash("¡Solicitud enviada! El rescatista se pondrá en contacto pronto.", "success")
        return redirect(url_for("pets.detail", pet_id=pet.id))
    return render_template("adoptions/form.html", form=form, pet=pet,
                           title=f"Solicitar adopción — {pet.display_name}")


@adoptions_bp.route("/mis-solicitudes")
@jwt_required
def my_requests():
    reqs = AdoptionRequest.query.filter_by(applicant_id=current_user.id)\
               .order_by(AdoptionRequest.created_at.desc()).all()
    return render_template("adoptions/my_requests.html", requests=reqs, title="Mis solicitudes")


@adoptions_bp.route("/revisar/<int:req_id>", methods=["GET", "POST"])
@jwt_required
def review(req_id):
    req = AdoptionRequest.query.get_or_404(req_id)
    pet = req.pet
    if not current_user.is_rescuer and pet.reporter_id != current_user.id:
        abort(403)

    if request.method == "POST":
        action = request.form.get("action")
        notes  = request.form.get("notes_rescuer", "").strip()
        if action in ("approve", "reject"):
            req.status = AdoptionStatus.APPROVED if action == "approve" else AdoptionStatus.REJECTED
            req.notes_rescuer = notes or None
            if action == "approve":
                old_status = pet.status
                pet.status = PetStatus.ADOPTED
                db.session.add(PetStatusLog(pet_id=pet.id, old_status=old_status,
                                            new_status=PetStatus.ADOPTED,
                                            changed_by=current_user.id,
                                            note=f"Solicitud #{req.id} aprobada"))
                # Rechazar las demás pendientes
                AdoptionRequest.query.filter(
                    AdoptionRequest.pet_id == pet.id,
                    AdoptionRequest.status == AdoptionStatus.PENDING,
                    AdoptionRequest.id != req.id
                ).update({"status": AdoptionStatus.REJECTED,
                          "notes_rescuer": "Otra solicitud fue aprobada."})
            # Notificar al solicitante
            result_msg = "¡Tu solicitud fue aprobada! 🎉" if action == "approve" \
                         else "Tu solicitud fue rechazada."
            create_notification(
                req.applicant_id, NotifType.ADOPTION_RESULT,
                "Resultado de tu solicitud",
                f"{result_msg} ({pet.display_name})",
                url_for("adoptions.my_requests")
            )
            db.session.commit()
            flash("Solicitud actualizada.", "success")
            return redirect(url_for("adoptions.pet_requests", pet_id=pet.id))

    return render_template("adoptions/review.html", req=req, pet=pet, title="Revisar solicitud")


@adoptions_bp.route("/mascota/<int:pet_id>/solicitudes")
@jwt_required
def pet_requests(pet_id):
    pet = Pet.query.get_or_404(pet_id)
    if not current_user.is_rescuer and pet.reporter_id != current_user.id:
        abort(403)
    reqs = AdoptionRequest.query.filter_by(pet_id=pet_id)\
               .order_by(AdoptionRequest.created_at.desc()).all()
    return render_template("adoptions/pet_requests.html", pet=pet, requests=reqs,
                           title=f"Solicitudes — {pet.display_name}")
