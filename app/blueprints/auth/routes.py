"""Blueprint de autenticación: registro, login, logout, perfil con JWT."""
from flask import Blueprint, render_template, redirect, url_for, flash, request, make_response, g
from app.models import db, User, UserQuiz
from .forms import RegisterForm, LoginForm, EditProfileForm, ChangePasswordForm
from app.utils import generate_jwt, jwt_required
from app.services.ai_service import evaluate_adoption_quiz

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/registro", methods=["GET", "POST"])
def register():
    # Usamos g.current_user definido en el hook before_request de __init__.py
    if g.current_user:
        return redirect(url_for("main.index"))
    
    form = RegisterForm()
    if form.validate_on_submit():
        user = User(
            full_name=form.full_name.data,
            username=form.username.data,
            email=form.email.data.lower(),
            phone_whatsapp=form.phone_whatsapp.data or None,
        )
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        flash("¡Cuenta creada exitosamente! Ya puedes iniciar sesión.", "success")
        return redirect(url_for("auth.login"))
    return render_template("auth/register.html", form=form, title="Registro")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if g.current_user:
        return redirect(url_for("main.index"))
    
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data.lower()).first()
        if user and user.check_password(form.password.data) and user.is_active:
            # Generar el Token JWT
            token = generate_jwt(user.id)
            
            flash(f"¡Bienvenido, {user.full_name}!", "success")
            next_page = request.args.get("next")
            
            # Crear la respuesta para setear la Cookie HttpOnly
            resp = make_response(redirect(next_page or url_for("main.index")))
            resp.set_cookie(
                'access_token',
                token,
                httponly=True,   # Protege contra lectura de JS (XSS)
                secure=False,    # Cambiar a True si usas HTTPS (Producción)
                samesite='Lax'
            )
            return resp
            
        flash("Correo o contraseña incorrectos.", "danger")
    return render_template("auth/login.html", form=form, title="Iniciar sesión")


@auth_bp.route("/logout")
def logout():
    """Cierra la sesión eliminando la cookie del token."""
    flash("Sesión cerrada.", "info")
    resp = make_response(redirect(url_for("main.index")))
    resp.delete_cookie('access_token')
    return resp


@auth_bp.route("/perfil")
@jwt_required
def profile():
    # Accedemos a los datos a través de g.current_user
    pets_reported = g.current_user.reported_pets.filter_by(is_active=True).all()
    return render_template("auth/profile.html", title="Mi perfil", pets=pets_reported)


@auth_bp.route("/perfil/editar", methods=["GET", "POST"])
@jwt_required
def edit_profile():
    # Se pasa g.current_user al formulario para precargar datos
    form = EditProfileForm(obj=g.current_user)
    if form.validate_on_submit():
        g.current_user.full_name = form.full_name.data
        g.current_user.phone_whatsapp = form.phone_whatsapp.data or None
        g.current_user.bio = form.bio.data or None
        db.session.commit()
        flash("Perfil actualizado.", "success")
        return redirect(url_for("auth.profile"))
    return render_template("auth/edit_profile.html", form=form, title="Editar perfil")


@auth_bp.route("/perfil/contrasena", methods=["GET", "POST"])
@jwt_required
def change_password():
    form = ChangePasswordForm()
    if form.validate_on_submit():
        if not g.current_user.check_password(form.current.data):
            flash("La contraseña actual es incorrecta.", "danger")
        else:
            g.current_user.set_password(form.new_pass.data)
            db.session.commit()
            flash("Contraseña actualizada correctamente.", "success")
            return redirect(url_for("auth.profile"))
    return render_template("auth/change_password.html", form=form, title="Cambiar contraseña")

@auth_bp.route("/verificar-cuenta", methods=["GET", "POST"])
# @jwt_required o @login_required (según lo que uses para proteger la ruta)
def take_quiz():
    # Obtener el usuario actual
    user = User.query.get(g.current_user.id)

    # REGLA 1: Bloqueo de usuarios ya verificados
    if user.is_verified:
        flash("Tu cuenta ya ha sido verificada. No necesitas enviar más solicitudes.", "info")
        return redirect(url_for('auth.profile')) # Ajusta el nombre de la vista si es distinto

    # REGLA 2: Evitar múltiples formularios pendientes
    quiz_existente = UserQuiz.query.filter(
        UserQuiz.user_id == user.id, 
        UserQuiz.status.ilike('pendiente')
    ).first()
    
    if quiz_existente:
        flash("Ya tienes una solicitud en revisión. Por favor espera a que un administrador la evalúe.", "warning")
        return redirect(url_for('auth.profile'))

    # PROCESAMIENTO DEL FORMULARIO
    if request.method == "POST":
        # 1. Recolectar las respuestas del formulario
        # Ajusta los nombres de las claves según los 'name' de tus <input> en el HTML
        answers = {
            "vivienda": request.form.get("vivienda"),
            "tiempo_solo": request.form.get("tiempo_solo"),
            "experiencia": request.form.get("experiencia"),
            "presupuesto": request.form.get("presupuesto")
        }

        # 2. Enviar a Gemini para evaluación
        resultado_ia = evaluate_adoption_quiz(answers)

        # 3. Crear el registro en la base de datos con los nombres exactos de tu modelo
        nuevo_quiz = UserQuiz(
            user_id=user.id,
            answers_json=answers,
            ai_score=resultado_ia.get("score", 0),
            ai_feedback=resultado_ia.get("recommendation", "Fallo al obtener análisis."),
            status="pendiente"
        )

        # 4. Guardar cambios
        db.session.add(nuevo_quiz)
        db.session.commit()

        flash("¡Cuestionario enviado con éxito! Los administradores revisarán la evaluación de la IA.", "success")
        return redirect(url_for('auth.profile'))

    # Si es GET, simplemente mostrar la página del cuestionario
    return render_template("auth/quiz.html")