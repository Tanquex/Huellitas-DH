from google import genai
import json
import logging

logger = logging.getLogger(__name__)

def evaluate_adoption_quiz(answers):
    # PON AQUÍ LA LLAVE NUEVA QUE SÍ FUNCIONÓ
    api_key = "AIzaSyAmWz4ChRbmuYZnKNQOJneY-j0btYIzWQM" 

    if not api_key or api_key.startswith("AIzaSyTu"):
        return {"score": 50, "recommendation": "Pon la llave real en el código"}

    try:
        # Quitamos la configuración de v1. Dejamos que el SDK fluya por defecto.
        client = genai.Client(api_key=api_key)
        
        # Volvemos al 2.0 lite que sí estaba en tus logs originales
        model_id = "gemini-2.5-flash"
        
        prompt = f"""
        Actúa como un evaluador experto en bienestar animal para 'Huellitas Unidas'.
        Analiza este cuestionario: {json.dumps(answers, ensure_ascii=False)}
        
        Criterios: 90-100 (Ideal), 70-89 (Bueno), 50-69 (Dudoso), 0-49 (No apto).
        
        Responde ÚNICAMENTE con un JSON válido con esta estructura exacta, sin texto extra, sin saludos y sin formato Markdown:
        {{"score": 85, "recommendation": "Tu análisis aquí justificando la puntuación."}}
        """
        
        logger.info(f"Enviando petición final a {model_id}...")
        
        response = client.models.generate_content(
            model=model_id,
            contents=prompt
        )
        
        # Pelamos el JSON por si la IA se pone creativa con el formato
        text = response.text.strip()
        if text.startswith("```"):
            text = text.replace("```json", "").replace("```", "").strip()
            
        logger.info(f"¡ÉXITO! Respuesta de Gemini: {text}")
        
        return json.loads(text)

    except Exception as e:
        logger.error(f"Error real capturado: {str(e)}")
        return {"score": 50, "recommendation": f"Fallo al procesar: {str(e)[:40]}"}