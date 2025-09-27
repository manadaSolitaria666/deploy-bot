import os
import json
import io
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)
import gspread
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from googleapiclient.errors import HttpError
import pypdf  # Se añade una nueva librería para leer el contenido de los PDFs

# --- CONFIGURACIÓN CENTRALIZADA Y SEGURA ---
# Leemos las variables desde el entorno del sistema (mejor para seguridad y despliegue)
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "7264211512:AAHHNuwEO--xk38E0sSuGCqcklilChd__nw") # Usa el token del entorno o el de respaldo
DRIVE_FOLDER_ID = os.environ.get("DRIVE_FOLDER_ID", "1NlS0qe7oRh7cq0fIPmxTnBDNz7nLMYXB")
SPREADSHEET_NAME = os.environ.get("SPREADSHEET_NAME", "Candidatos Bot")

# --- Constantes para validación (más fácil de mantener) ---
CARRERAS_VALIDAS = [
    "ingeniería", "sistemas", "computación", "computacion", "informática", 
    "informatica", "software", "ciberseguridad", "tecnologías de la información", 
    "tics", "desarrollo"
]
ESPECIALIDADES_VALIDAS = ["ing.software", "ciberseguridad", "desarrollo de software"]

# --- BLOQUE DE CONFIGURACIÓN DE GOOGLE (Adaptado para Despliegue) ---
SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
creds = None

# Prioriza leer credenciales desde variables de entorno (para Railway/Heroku)
client_secret_json_str = os.environ.get('GOOGLE_CLIENT_SECRET_JSON')
token_json_str = os.environ.get('GOOGLE_TOKEN_JSON')

if client_secret_json_str and token_json_str:
    # Si estamos en un servidor (como Railway), crea los archivos a partir de las variables
    with open('client_secret.json', 'w') as f:
        f.write(client_secret_json_str)
    with open('token.json', 'w') as f:
        f.write(token_json_str)

# Proceso de autenticación estándar
if os.path.exists("token.json"):
    creds = Credentials.from_authorized_user_file("token.json", SCOPES)

# Si no hay credenciales válidas (ej. la primera vez que se ejecuta localmente)
if not creds or not creds.valid:
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    else:
        # Este flujo solo se ejecutará si NO estamos en un servidor y no hay token.json
        if os.path.exists('client_secret.json'):
            flow = InstalledAppFlow.from_client_secrets_file("client_secret.json", SCOPES)
            creds = flow.run_local_server(port=0)
        else:
            print("ERROR: Faltan las credenciales de Google. Sigue las instrucciones del README.")
            # Salir si no hay forma de autenticarse
            exit()
    
    with open("token.json", "w") as token:
        token.write(creds.to_json())

# Construye los servicios de Drive y Sheets con las credenciales autorizadas.
try:
    drive_service = build("drive", "v3", credentials=creds)
    gc = gspread.authorize(creds)
    sheet = gc.open(SPREADSHEET_NAME).sheet1
except Exception as e:
    print(f"Error al conectar con los servicios de Google: {e}")
    exit()
# --- FIN DEL BLOQUE DE CONFIGURACIÓN ---


# --- Función de validación de CV ---
def es_un_cv_valido(ruta_archivo: str) -> bool:
    """Extrae texto del PDF y busca palabras clave para validar si es un CV."""
    try:
        texto_completo = ""
        with open(ruta_archivo, "rb") as f:
            reader = pypdf.PdfReader(f)
            if not reader.pages:
                return False  # PDF vacío
            for page in reader.pages:
                texto_completo += page.extract_text() or ""

        texto_minusculas = texto_completo.lower()

        palabras_clave_cv = [
            "experiencia", "experience", "educación", "education", "habilidades",
            "skills", "referencias", "references", "objetivo", "summary",
            "perfil", "profile", "proyectos", "projects", "certificaciones",
            "certifications", "cursos", "courses", "idiomas", "languages",
            "curriculum vitae", "cv", "resume", "aptitudes"
        ]

        # Contamos cuántas palabras clave únicas se encontraron
        contador_palabras = sum(1 for palabra in palabras_clave_cv if palabra in texto_minusculas)
        
        # Consideramos que es un CV si se encuentran al menos 3 palabras clave diferentes
        print(f"Palabras clave de CV encontradas: {contador_palabras}")
        return contador_palabras >= 3

    except Exception as e:
        print(f"Error al validar el contenido del PDF: {e}")
        return False # Si no se puede leer, no es un CV válido para nosotros

# --- Lógica del Bot (con nuevo paso "CARRERA") ---
# Definición de los estados de la conversación
NOMBRE, EDAD, EXPERIENCIA, INGLES, CARRERA, ESPECIALIDAD, CV = range(7)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia la conversación."""
    await update.message.reply_text("¡Hola! Bienvenido al proceso de selección. Por favor, responde a las siguientes preguntas.\n\n¿Cuál es tu nombre?")
    return NOMBRE

async def recibir_nombre(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Guarda el nombre y pregunta la edad."""
    context.user_data['nombre'] = update.message.text
    await update.message.reply_text("¿Cuál es tu edad?")
    return EDAD

async def recibir_edad(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Guarda la edad, la valida y pregunta la experiencia."""
    try:
        edad = int(update.message.text)
        if edad < 18:
            await update.message.reply_text("Lo sentimos, debes ser mayor de 20 años para continuar. Proceso finalizado.")
            return ConversationHandler.END
        context.user_data['edad'] = edad
        await update.message.reply_text("¿Cuántos años de experiencia tienes?")
        return EXPERIENCIA
    except ValueError:
        await update.message.reply_text("Por favor, introduce un número válido para tu edad.")
        return EDAD

async def recibir_experiencia(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Guarda la experiencia, la valida y pregunta el nivel de inglés."""
    try:
        experiencia = int(update.message.text)
        if experiencia < 2:
            await update.message.reply_text("Lo sentimos, se requieren al menos 2 años de experiencia. Proceso finalizado.")
            return ConversationHandler.END
        context.user_data['experiencia'] = experiencia
        await update.message.reply_text("¿Cuál es tu porcentaje de inglés? (ej. 80)")
        return INGLES
    except ValueError:
        await update.message.reply_text("Por favor, introduce un número válido para tus años de experiencia.")
        return EXPERIENCIA

async def recibir_ingles(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Guarda el nivel de inglés, lo valida y pregunta la carrera."""
    try:
        ingles = int(update.message.text.replace('%', ''))
        if ingles < 80:
            await update.message.reply_text("Lo sentimos, se requiere un mínimo de 40% de inglés. Proceso finalizado.")
            return ConversationHandler.END
        context.user_data['ingles'] = ingles
        await update.message.reply_text("Gracias. Ahora, ¿cuál es tu carrera universitaria?")
        return CARRERA
    except ValueError:
        await update.message.reply_text("Por favor, introduce un número válido para tu porcentaje de inglés.")
        return INGLES

async def recibir_carrera(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Guarda la carrera, la valida y pregunta la especialidad."""
    carrera = update.message.text.lower()
    if any(keyword in carrera for keyword in CARRERAS_VALIDAS):
        context.user_data['carrera'] = update.message.text
        await update.message.reply_text("Carrera válida. ¿Cuál es tu área de especialidad? (ej. ing. software, ciberseguridad, desarrollo de software)")
        return ESPECIALIDAD
    else:
        await update.message.reply_text("Lo sentimos, buscamos perfiles con carreras relacionadas a la tecnología. Proceso finalizado.")
        return ConversationHandler.END

async def recibir_especialidad(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Guarda la especialidad, la valida y pide el CV."""
    especialidad = update.message.text.lower()
    if especialidad not in ESPECIALIDADES_VALIDAS:
        await update.message.reply_text("Lo sentimos, tu área de especialidad no coincide con las requeridas. Proceso finalizado.")
        return ConversationHandler.END
    context.user_data['especialidad'] = especialidad
    await update.message.reply_text("Gracias. Por favor, sube tu CV en formato PDF.")
    return CV

async def recibir_cv(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recibe el CV, lo sube a Drive y guarda toda la información en Sheets."""
    documento = update.message.document
    if not (documento and documento.mime_type == 'application/pdf'):
        await update.message.reply_text("Por favor, envía un archivo en formato PDF.")
        return CV

    ruta_archivo = f"{documento.file_id}.pdf"
    try:
        archivo = await documento.get_file()
        await archivo.download_to_drive(ruta_archivo)

        # ¡NUEVA VALIDACIÓN DE CONTENIDO!
        if not es_un_cv_valido(ruta_archivo):
            await update.message.reply_text("El archivo PDF no parece ser un CV válido. Por favor, sube tu currículum.")
            return CV # Nos quedamos en el estado CV para que el usuario pueda reintentar

        file_metadata = {'name': f"{context.user_data.get('nombre', 'candidato')}_CV.pdf", 'parents': [DRIVE_FOLDER_ID]}
        
        # --- CAMBIO PRINCIPAL: Uso de 'with' para garantizar el cierre del archivo ---
        # Esto asegura que el archivo se cierre correctamente y evita problemas de
        # permisos en Windows al intentar borrarlo en el bloque 'finally'.
        with open(ruta_archivo, 'rb') as fh:
            media = MediaIoBaseUpload(fh, mimetype='application/pdf', resumable=True)
            
            file = drive_service.files().create(
                body=file_metadata,
                media_body=media,
                fields='webViewLink'
            ).execute()
        
        enlace_cv = file.get('webViewLink')

        # Guardar en Google Sheets
        fila = [
            context.user_data.get('nombre', 'N/A'),
            context.user_data.get('edad', 'N/A'),
            context.user_data.get('experiencia', 'N/A'),
            context.user_data.get('ingles', 'N/A'),
            context.user_data.get('carrera', 'N/A'),
            context.user_data.get('especialidad', 'N/A'),
            enlace_cv
        ]
        sheet.append_row(fila)

        await update.message.reply_text("¡Hemos recibido tu CV! GRACIAS POR COMUNICARSE CON NOSOTROS Gracias por completar el proceso. Nos pondremos en contacto contigo pronto.")

    except HttpError as error:
        print(f"Ocurrió un error con la API de Google: {error}")
        await update.message.reply_text("Lo siento, ocurrió un error al procesar tu CV. Por favor, contacta al administrador.")
    except Exception as e:
        print(f"Ocurrió un error inesperado: {e}")
        await update.message.reply_text("Lo siento, ocurrió un error inesperado. Inténtalo de nuevo más tarde.")
    finally:
        # Asegura que el archivo temporal se elimine siempre, sin importar si hubo éxito o error.
        if os.path.exists(ruta_archivo):
            os.remove(ruta_archivo)
            
    return ConversationHandler.END

async def cancelar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancela la conversación."""
    await update.message.reply_text("Proceso cancelado.")
    return ConversationHandler.END

def main() -> None:
    """Inicia el bot."""
    if not TELEGRAM_TOKEN:
        print("ERROR: No se encontró el TELEGRAM_TOKEN. El bot no puede iniciar.")
        return

    application = Application.builder().token(TELEGRAM_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            NOMBRE: [MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_nombre)],
            EDAD: [MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_edad)],
            EXPERIENCIA: [MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_experiencia)],
            INGLES: [MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_ingles)],
            CARRERA: [MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_carrera)],
            ESPECIALIDAD: [MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_especialidad)],
            CV: [MessageHandler(filters.Document.ALL, recibir_cv)],
        },
        fallbacks=[CommandHandler("cancelar", cancelar)],
    )

    application.add_handler(conv_handler)
    application.run_polling()

if __name__ == "__main__":

    main()








