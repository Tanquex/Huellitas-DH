"""app/__init__.py — Application Factory con Autenticación JWT."""
import os
import jwt
from flask import Flask, g, request
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFProtect
from .models import db, bcrypt, User
from config import config_map

# Inicialización de extensiones (sin LoginManager)
migrate = Migrate()
csrf    = CSRFProtect()

def create_app(env: str = None) -> Flask:
    app = Flask(__name__, instance_relative_config=False)

    # Configuración de entorno
    env = env or os.environ.get("FLASK_ENV", "development")
    app.config.from_object(config_map.get(env, config_map["development"]))

    # Inicializar extensiones con la app
    db.init_app(app)
    bcrypt.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)

    # --- LÓGICA DE IDENTIDAD JWT ---

    @app.before_request
    def load_jwt_user():
        """
        Extrae el token de la cookie en cada petición e intenta 
        identificar al usuario en el contexto global 'g'.
        """
        g.current_user = None
        token = request.cookies.get('access_token')
        
        if token:
            try:
                # Decodificación del token usando la SECRET_KEY de la app
                data = jwt.decode(
                    token, 
                    app.config.get('SECRET_KEY'), 
                    algorithms=['HS256']
                )
                # Buscamos al usuario en la base de datos
                g.current_user = db.session.get(User, data['sub'])
            except (jwt.ExpiredSignatureError, jwt.InvalidTokenError, Exception):
                # Si el token no es válido o expiró, g.current_user sigue siendo None
                pass

    @app.context_processor
    def inject_global_vars():
        """
        Inyecta variables en todas las plantillas Jinja2.
        Reemplaza la funcionalidad de 'current_user' que proveía Flask-Login.
        """
        from .utils import STATUS_COLOR
        return dict(
            current_user=g.current_user,
            STATUS_COLOR=STATUS_COLOR
        )

    # --- REGISTRO DE BLUEPRINTS ---
    
    from .blueprints.main.routes      import main_bp
    from .blueprints.auth.routes      import auth_bp
    from .blueprints.pets.routes      import pets_bp
    from .blueprints.adoptions.routes import adoptions_bp
    from .blueprints.admin.routes     import admin_bp
    from .blueprints.rescuer.routes   import rescuer_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp,      url_prefix="/auth")
    app.register_blueprint(pets_bp,      url_prefix="/mascotas")
    app.register_blueprint(adoptions_bp, url_prefix="/adopciones")
    app.register_blueprint(admin_bp,     url_prefix="/admin")
    app.register_blueprint(rescuer_bp,   url_prefix="/rescatista")

    # Asegurar directorio de subidas
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    # --- MANEJADORES DE ERRORES ---
    
    from .blueprints.main.routes import page_not_found, server_error, forbidden
    app.register_error_handler(403, forbidden)
    app.register_error_handler(404, page_not_found)
    app.register_error_handler(500, server_error)

    return app