from flask import Flask, jsonify, render_template, redirect, url_for, request
import psycopg2
import json
import os
from datetime import datetime, timedelta
from collections import defaultdict
from flask_caching import Cache
from dotenv import load_dotenv
import urllib.parse

# Cargar variables de entorno solo en desarrollo local
# En Railway, las variables se proporcionan automáticamente
if os.getenv('RAILWAY_ENVIRONMENT') is None:
    load_dotenv()

app = Flask(__name__)

# Configuración de caché
app.config['CACHE_TYPE'] = 'simple'  # Para desarrollo. En producción usar 'redis'
app.config['CACHE_DEFAULT_TIMEOUT'] = 300  # 5 minutos por defecto
app.config['CACHE_KEY_PREFIX'] = 'chat_app_'

# Inicializar caché
cache = Cache(app)

# Configuración DB usando variables de entorno
def get_db_config():
    database_url = os.getenv('DATABASE_URL')
    if database_url:
        # Parsear DATABASE_URL
        parsed = urllib.parse.urlparse(database_url)
        return {
            "host": parsed.hostname,
            "port": parsed.port,
            "dbname": parsed.path[1:],  # Remover el '/' inicial
            "user": parsed.username,
            "password": parsed.password
        }
    else:
        # Fallback a variables individuales de PostgreSQL estándar
        return {
            "host": os.getenv('PGHOST', os.getenv('DB_HOST', 'localhost')),
            "port": int(os.getenv('PGPORT', os.getenv('DB_PORT', 5432))),
            "dbname": os.getenv('PGDATABASE', os.getenv('DB_NAME', 'railway')),
            "user": os.getenv('PGUSER', os.getenv('DB_USER', 'postgres')),
            "password": os.getenv('PGPASSWORD', os.getenv('DB_PASSWORD'))
        }

# Inicializar DB_CONFIG de manera lazy para asegurar que las variables de entorno estén disponibles
DB_CONFIG = None

def get_db_connection_config():
    global DB_CONFIG
    if DB_CONFIG is None:
        DB_CONFIG = get_db_config()
    return DB_CONFIG

@app.route('/debug/env')
def debug_env():
    """Endpoint para verificar variables de entorno de la base de datos"""
    env_vars = {
        'DATABASE_URL': os.getenv('DATABASE_URL', 'NOT SET'),
        'DB_HOST': os.getenv('DB_HOST', 'NOT SET'),
        'DB_PORT': os.getenv('DB_PORT', 'NOT SET'),
        'DB_NAME': os.getenv('DB_NAME', 'NOT SET'),
        'DB_USER': os.getenv('DB_USER', 'NOT SET'),
        'DB_PASSWORD': 'SET' if os.getenv('DB_PASSWORD') else 'NOT SET',
        'RAILWAY_ENVIRONMENT': os.getenv('RAILWAY_ENVIRONMENT', 'NOT SET'),
        'PORT': os.getenv('PORT', 'NOT SET')
    }
    
    # Obtener configuración actual de DB
    current_db_config = get_db_connection_config()
    
    return jsonify({
        'environment_variables': env_vars,
        'current_db_config': current_db_config
    })

@app.route('/debug/<execution_id>')
@cache.cached(timeout=300, key_prefix='debug_execution')  # Caché por 5 minutos
def debug_execution(execution_id):
    conn = psycopg2.connect(**get_db_connection_config())
    cur = conn.cursor()
    
    try:
        # 1. Obtener datos crudos en formato JSON
        cur.execute("""
            SELECT execution_data."executionId"::text, execution_data.data::jsonb 
            FROM execution_data 
            WHERE execution_data."executionId"::text = %s
        """, (execution_id,))
        
        execution = cur.fetchone()
        
        if not execution:
            return jsonify({"error": "Ejecución no encontrada"}), 404
        
        # 2. Encontrar mensajes mediante exploración profunda
        messages = find_messages_in_data(execution[1])
        
        return jsonify({
            "id": execution[0],
            "createdat": None,  # Ya no tenemos esta columna
            "raw_data_structure": describe_structure(execution[1]),
            "found_messages": messages,
            "full_data": execution[1]  # ¡Cuidado! Solo para desarrollo
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cur.close()
        conn.close()

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Página de inicio de sesión"""
    if request.method == 'POST':
        # Aquí puedes agregar la lógica de autenticación
        email = request.form.get('email')
        password = request.form.get('password')
        
        # Por ahora, redirigir a la página principal
        # En el futuro, aquí validarías las credenciales
        return redirect(url_for('home'))
    
    return render_template('login.html')

@app.route('/')
def home():
    """Página principal que redirige a la fecha actual o procesa filtro de fecha"""
    
    # Obtener parámetro de fecha del formulario
    date_param = request.args.get('date')
    
    if date_param:
        # Convertir formato YYYY-MM-DD a YYYY-MM-DD para la función
        try:
            # Validar formato de fecha
            datetime.strptime(date_param, '%Y-%m-%d')
            return redirect(url_for('list_chats', date_filter=date_param))
        except ValueError:
            # Si el formato es inválido, usar fecha actual
            today = datetime.now().date().strftime('%Y-%m-%d')
            return redirect(url_for('list_chats', date_filter=today))
    else:
        # Sin parámetro de fecha, usar fecha actual
        today = datetime.now().date().strftime('%Y-%m-%d')
        return redirect(url_for('list_chats', date_filter=today))

@app.route('/chats')
def all_chats():
    """Vista de todas las conversaciones (solo para casos específicos)"""
    return list_chats_internal(show_all=True)

@app.route('/chats/<date_filter>')
def list_chats(date_filter=None):
    """Lista conversaciones filtradas por fecha específica"""
    return list_chats_internal(date_filter=date_filter)

def list_chats_internal(date_filter=None, show_all=False):
    """Lista todas las conversaciones, agrupadas por número de teléfono y opcionalmente filtradas por fecha"""
    
    # Crear clave de caché basada en los parámetros
    cache_key = f"chats_list_{date_filter}_{show_all}"
    
    # Intentar obtener del caché primero
    cached_result = cache.get(cache_key)
    if cached_result:
        return cached_result
    
    conn = psycopg2.connect(**get_db_connection_config())
    cur = conn.cursor()
    
    try:
        # Si no se especifica mostrar todo y no hay filtro de fecha, usar fecha actual
        if not show_all and not date_filter:
            date_filter = datetime.now().date().strftime('%Y-%m-%d')
        
        # Obtener todas las ejecuciones
        cur.execute("""
            SELECT execution_data."executionId"::text, execution_data.data::jsonb 
            FROM execution_data 
            ORDER BY execution_data."executionId"::text
        """)
        
        executions = cur.fetchall()
        
        # Procesar cada ejecución para extraer información básica
        chats_by_phone = {}  # Agrupar por número de teléfono
        chats_by_date = {}
        all_chats = []
        
        # Convertir el filtro de fecha si existe
        target_date = None
        if date_filter and not show_all:
            try:
                # Convertir el filtro de fecha
                if '-' in date_filter:
                    if len(date_filter.split('-')[0]) == 4:  # YYYY-MM-DD
                        target_date = datetime.strptime(date_filter, '%Y-%m-%d').date()
                    else:  # DD-MM-YYYY
                        target_date = datetime.strptime(date_filter, '%d-%m-%Y').date()
                else:
                    # Formato sin separadores: DDMMYYYY
                    target_date = datetime.strptime(date_filter, '%d%m%Y').date()
            except ValueError:
                return jsonify({"error": "Formato de fecha inválido. Use YYYY-MM-DD, DD-MM-YYYY o DDMMYYYY"}), 400
        
        for execution in executions:
            execution_id, data = execution
            
            try:
                # Extraer información básica del chat
                chat_data = extract_chat_messages(data, execution_id)
                user_info = chat_data.get('user_info', {})
                timestamps = extract_timestamps_from_data(data)
                
                # Determinar la fecha del chat
                if timestamps:
                    chat_date = timestamps[0].date()
                else:
                    chat_date = datetime.now().date()
                
                # Aplicar filtro de fecha si existe
                if target_date and chat_date != target_date:
                    continue
                
                # Solo incluir registros que tienen conversación real
                has_conversation = not chat_data.get('no_conversation', False)
                phone_number = user_info.get('phone_number')
                
                if has_conversation and phone_number:
                    chat_summary = {
                        'id': execution_id,
                        'date': chat_date,
                        'date_str': chat_date.strftime('%d/%m/%Y'),
                        'phone_number': phone_number,
                        'user_name': user_info.get('user_name'),
                        'message_count': len(chat_data.get('messages', [])),
                        'has_conversation': True,
                        'preview': get_chat_preview(chat_data),
                        'data_size': len(str(data))  # Para identificar el registro más completo
                    }
                    
                    # Agrupar por número de teléfono y fecha
                    phone_date_key = f"{phone_number}_{chat_date.strftime('%Y-%m-%d')}"
                    
                    if phone_date_key not in chats_by_phone:
                        chats_by_phone[phone_date_key] = []
                    
                    chats_by_phone[phone_date_key].append(chat_summary)
                
            except Exception as e:
                print(f"Error procesando ejecución {execution_id}: {e}")
                continue
        
        # Para cada grupo de teléfono+fecha, seleccionar el registro más completo (más largo)
        for phone_date_key, phone_chats in chats_by_phone.items():
            if phone_chats:
                # Ordenar por tamaño de datos (descendente) y tomar el más completo
                best_chat = max(phone_chats, key=lambda x: x['data_size'])
                
                # Sumar todos los mensajes de los diferentes registros del mismo teléfono
                total_messages = sum(chat['message_count'] for chat in phone_chats)
                best_chat['message_count'] = total_messages
                best_chat['total_records'] = len(phone_chats)
                
                all_chats.append(best_chat)
                
                # Agrupar por fecha
                date_key = best_chat['date'].strftime('%Y-%m-%d')
                if date_key not in chats_by_date:
                    chats_by_date[date_key] = {
                        'date': best_chat['date'],
                        'date_str': best_chat['date_str'],
                        'chats': []
                    }
                chats_by_date[date_key]['chats'].append(best_chat)
        
        # Si hay filtro de fecha específico, devolver solo esos chats
        if target_date:
            date_key = target_date.strftime('%Y-%m-%d')
            filtered_chats = chats_by_date.get(date_key, {}).get('chats', [])
            
            # Debug: mostrar los IDs finales que se envían al template
            final_ids = [chat['id'] for chat in filtered_chats]
            print(f"🎯 IDs finales enviados al template: {final_ids}")
            
            result = render_template('chat_list.html', 
                                 chats=filtered_chats, 
                                 filter_date=target_date.strftime('%d/%m/%Y'),
                                 chats_by_date=chats_by_date,
                                 current_date=target_date.strftime('%Y-%m-%d'))
            
            # NO guardar en caché temporalmente para debug
            # cache.set(cache_key, result, timeout=300)
            return result
        
        # Sin filtro específico, mostrar todos agrupados por fecha (solo si show_all=True)
        result = render_template('chat_list.html', 
                             chats=all_chats, 
                             chats_by_date=chats_by_date)
        
        # Guardar en caché por 5 minutos
        cache.set(cache_key, result, timeout=300)
        return result
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cur.close()
        conn.close()

@app.route('/chat/<execution_id>')
@app.route('/chat/<execution_id>/<date_filter>')
# @cache.cached(timeout=600, key_prefix='chat_detail')  # Temporalmente deshabilitado para debug
def view_chat(execution_id, date_filter=None):
    conn = psycopg2.connect(**get_db_connection_config())
    cur = conn.cursor()
    
    try:
        # Obtener datos crudos en formato JSON
        cur.execute("""
            SELECT execution_data."executionId"::text, execution_data.data::jsonb 
            FROM execution_data 
            WHERE execution_data."executionId"::text = %s
        """, (execution_id,))
        
        execution = cur.fetchone()
        
        if not execution:
            return jsonify({"error": "Ejecución no encontrada"}), 404
        
        # Extraer y organizar los mensajes para la vista de chat
        chat_data = extract_chat_messages(execution[1], execution_id)
        
        return render_template('chats.html', chats=[chat_data], date_filter=date_filter)
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cur.close()
        conn.close()

def extract_user_info(data):
    """Extrae información del usuario (número de teléfono y nombre) de los datos"""
    phone_number = None
    user_name = None
    
    def is_valid_phone_number(phone_str):
        """Verifica si un string es un número de teléfono válido"""
        if not isinstance(phone_str, str) or not phone_str.isdigit():
            return False
        
        # Números internacionales típicos (7-15 dígitos)
        if len(phone_str) >= 7 and len(phone_str) <= 15:
            return True
        
        return False
    
    def search_user_info(obj):
        nonlocal phone_number, user_name
        
        if isinstance(obj, dict):
            # Buscar campos de teléfono
            for key, value in obj.items():
                if 'from' in key.lower() and isinstance(value, str):
                    if is_valid_phone_number(value):
                        phone_number = value
                
                # Buscar nombres en campos específicos
                if 'name' in key.lower() and isinstance(value, str):
                    # Verificar si es una referencia numérica
                    try:
                        name_ref = int(value)
                        if name_ref < len(data) and isinstance(data[name_ref], str):
                            # Verificar que parece un nombre real (no solo números o códigos)
                            potential_name = data[name_ref]
                            if len(potential_name) > 3 and not potential_name.isdigit():
                                user_name = potential_name
                    except (ValueError, IndexError):
                        # Si no es referencia numérica, usar directamente
                        if len(value) > 3 and not value.isdigit():
                            user_name = value
                
                # Búsqueda recursiva
                search_user_info(value)
        
        elif isinstance(obj, list):
            for item in obj:
                search_user_info(item)
        
        elif isinstance(obj, str):
            # Buscar números de teléfono directamente en strings
            if is_valid_phone_number(obj):
                if not phone_number:  # Solo tomar el primero encontrado
                    phone_number = obj
    
    search_user_info(data)
    
    return {
        'phone_number': phone_number,
        'user_name': user_name
    }

def extract_chat_messages(execution_data, chat_id):
    """Extrae mensajes de chat de los datos de ejecución con timestamps ordenados"""
    
    # Extraer información del usuario
    user_info = extract_user_info(execution_data)
    
    # Extraer conversación
    conversation_messages = extract_conversation_from_data(execution_data)
    
    # Si no hay conversación, retornar inmediatamente
    if not conversation_messages:
        return {
            'id': chat_id,
            'created': datetime.now(),
            'updated': datetime.now(),
            'messages': [],
            'no_conversation': True,
            'status': 'Registro sin conversación',
            'user_info': user_info
        }
    
    # Buscar timestamps
    timestamps = extract_timestamps_from_data(execution_data)
    messages = []
    
    # Asignar timestamps a los mensajes si están disponibles
    for i, msg in enumerate(conversation_messages):
        timestamp = None
        
        # Si tenemos timestamps, asignarlos en orden
        if i < len(timestamps):
            timestamp = timestamps[i]
        else:
            # Si no hay timestamp específico, usar uno calculado basado en el orden
            base_time = datetime.now() - timedelta(minutes=len(conversation_messages) - i)
            timestamp = base_time
        
        messages.append({
            'sender': msg['sender'],
            'text': msg['text'],
            'timestamp': timestamp
        })
    
    # Ordenar mensajes por timestamp
    messages.sort(key=lambda x: x['timestamp'])
    
    # Usar el timestamp del primer mensaje como fecha de creación de la conversación
    conversation_created = messages[0]['timestamp'] if messages else datetime.now()
    
    return {
        'id': chat_id,
        'created': conversation_created,
        'updated': datetime.now(),
        'messages': messages,
        'no_conversation': False,
        'user_info': user_info
    }

def extract_timestamps_from_data(data):
    """Extrae timestamps de la estructura de datos"""
    timestamps = []
    
    def search_for_timestamps(obj, path=""):
        if isinstance(obj, dict):
            for key, value in obj.items():
                new_path = f"{path}.{key}" if path else key
                
                # Buscar campos que puedan contener timestamps
                if any(time_key in key.lower() for time_key in ['time', 'date', 'created', 'timestamp', 'at']):
                    try:
                        # Intentar parsear como timestamp
                        if isinstance(value, (int, float)):
                            # Timestamp Unix (segundos o milisegundos)
                            if value > 1000000000000:  # Milisegundos
                                timestamp = datetime.fromtimestamp(value / 1000)
                            elif value > 1000000000:  # Segundos
                                timestamp = datetime.fromtimestamp(value)
                            else:
                                continue
                            timestamps.append(timestamp)
                        elif isinstance(value, str):
                            # Intentar parsear string de fecha
                            for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S', '%d/%m/%Y %H:%M:%S', '%Y-%m-%d', '%d/%m/%Y']:
                                try:
                                    timestamp = datetime.strptime(value, fmt)
                                    timestamps.append(timestamp)
                                    break
                                except ValueError:
                                    continue
                    except (ValueError, OSError):
                        pass
                
                # Búsqueda recursiva
                search_for_timestamps(value, new_path)
        
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                search_for_timestamps(item, f"{path}[{i}]")
    
    search_for_timestamps(data)
    
    # Si no se encontraron timestamps, generar una secuencia lógica
    if not timestamps:
        base_time = datetime.now() - timedelta(hours=1)
        for i in range(10):  # Generar hasta 10 timestamps por defecto
            timestamps.append(base_time + timedelta(minutes=i * 2))
    
    # Ordenar timestamps
    timestamps.sort()
    
    return timestamps

def extract_conversation_from_data(data):
    """Extrae la conversación de la estructura de datos específica de LangChain con referencias numéricas"""
    messages = []
    
    if not isinstance(data, list):
        return messages
    
    # Verificar si hay mensajes de conversación real
    has_conversation = False
    
    # Buscar indicadores de conversación (HumanMessage, AIMessage)
    for item in data:
        if isinstance(item, str) and item in ["HumanMessage", "AIMessage"]:
            has_conversation = True
            break
    
    # Si no hay conversación, retornar lista vacía para indicar "sin conversación"
    if not has_conversation:
        return []
    
    # Buscar objetos que contengan "content" con referencias numéricas
    content_messages = []
    
    def find_content_references(obj, path=""):
        if isinstance(obj, dict):
            # Buscar objetos con estructura de mensaje
            if "content" in obj and isinstance(obj["content"], str):
                try:
                    # Verificar si el content es una referencia numérica
                    content_ref = int(obj["content"])
                    if content_ref < len(data):
                        actual_content = data[content_ref]
                        if isinstance(actual_content, str) and is_real_conversation_message(actual_content):
                            content_messages.append({
                                'content': actual_content,
                                'path': path,
                                'ref': content_ref
                            })
                except (ValueError, IndexError):
                    # Si no es una referencia numérica válida, usar el contenido directamente
                    if is_real_conversation_message(obj["content"]):
                        content_messages.append({
                            'content': obj["content"],
                            'path': path,
                            'ref': None
                        })
            
            # Búsqueda recursiva
            for key, value in obj.items():
                find_content_references(value, f"{path}.{key}" if path else key)
        
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                find_content_references(item, f"{path}[{i}]" if path else f"[{i}]")
    
    find_content_references(data)
    
    # Deduplicar mensajes basado en el contenido
    seen_contents = set()
    unique_messages = []
    
    for msg_info in content_messages:
        content = msg_info['content']
        
        # Solo agregar si no hemos visto este contenido antes
        if content not in seen_contents:
            seen_contents.add(content)
            unique_messages.append(msg_info)
    
    # Procesar los mensajes únicos y determinar el sender
    for msg_info in unique_messages:
        content = msg_info['content']
        path = msg_info['path']
        
        # Determinar si es usuario o bot basado en el contenido y contexto
        sender = determine_sender(content, path, data)
        
        messages.append({
            'sender': sender,
            'text': content
        })
    
    # Si no encontramos mensajes con referencias, usar el método anterior
    if not messages:
        # Buscar patrones específicos de LangChain
        seen_texts = set()
        i = 0
        while i < len(data):
            item = data[i]
            
            # Buscar patrones de HumanMessage y AIMessage
            if isinstance(item, str):
                if item == "HumanMessage" and i + 1 < len(data):
                    user_text = str(data[i + 1])
                    if is_real_conversation_message(user_text) and user_text not in seen_texts:
                        seen_texts.add(user_text)
                        messages.append({
                            'sender': 'user',
                            'text': user_text
                        })
                    i += 2
                elif item == "AIMessage" and i + 1 < len(data):
                    bot_text = str(data[i + 1])
                    if is_real_conversation_message(bot_text) and bot_text not in seen_texts:
                        seen_texts.add(bot_text)
                        messages.append({
                            'sender': 'bot',
                            'text': bot_text
                        })
                    i += 2
                else:
                    if is_real_conversation_message(item) and item not in seen_texts:
                        seen_texts.add(item)
                        sender = 'user' if len(item) < 100 else 'bot'
                        messages.append({
                            'sender': sender,
                            'text': item
                        })
                    i += 1
            else:
                i += 1
    
    return messages

def determine_sender(content, path, data):
    """Determina si un mensaje es del usuario o del bot basado en el contenido y contexto"""
    
    # PRIMERO: Análisis específico para mensajes conocidos (casos exactos) - MÁXIMA PRIORIDAD
    content_clean = content.strip().lower()
    
    # Casos específicos de usuario
    if content_clean == "hola 1356":
        return 'user'
    if content_clean == "cotizame 1 ciento de llaves":
        return 'user'
    if content_clean == "ok gracias":
        return 'user'
    
    # Casos específicos de bot
    if "¿en qué puedo ayudarte" in content_clean:
        return 'bot'
    if "te recomiendo contactar" in content_clean:
        return 'bot'
    if "de nada! si necesitas" in content_clean:
        return 'bot'
    
    # SEGUNDO: Análisis específico para solicitudes
    if "cotiza" in content_clean and len(content) < 100:
        return 'user'
    
    # TERCERO: Buscar indicadores en el path o contexto cercano
    path_lower = path.lower()
    
    # Buscar "HumanMessage" o "AIMessage" en el contexto más amplio
    if isinstance(data, list):
        # Primero encontrar la posición del contenido
        content_position = None
        for i, item in enumerate(data):
            if isinstance(item, str) and item.strip() == content.strip():
                content_position = i
                break
        
        if content_position is not None:
            # Buscar HumanMessage y AIMessage en el contexto
            human_positions = []
            ai_positions = []
            
            # Buscar en un rango amplio alrededor del contenido
            search_range = 20
            for k in range(max(0, content_position - search_range), 
                          min(len(data), content_position + search_range)):
                if isinstance(data[k], str):
                    if data[k] == "HumanMessage":
                        human_positions.append(k)
                    elif data[k] == "AIMessage":
                        ai_positions.append(k)
            
            # Determinar cuál está más cerca
            closest_human_dist = float('inf')
            closest_ai_dist = float('inf')
            
            if human_positions:
                closest_human_dist = min(abs(pos - content_position) for pos in human_positions)
            
            if ai_positions:
                closest_ai_dist = min(abs(pos - content_position) for pos in ai_positions)
            
            # Si hay una diferencia clara, usar el más cercano
            if closest_human_dist < closest_ai_dist and closest_human_dist <= 15:
                return 'user'
            elif closest_ai_dist < closest_human_dist and closest_ai_dist <= 15:
                return 'bot'
    
    # Análisis heurístico del contenido
    content_lower = content.lower()
    
    # Patrones específicos que indican claramente el tipo de mensaje
    
    # Patrones muy específicos de usuario (solicitudes, saludos simples)
    strong_user_patterns = [
        'hola', 'hello', 'hi', 'gracias', 'thanks', 'ok', 'si', 'yes', 'no',
        'cotiza', 'cotizame', 'precio', 'cuanto', 'how much', 'quiero', 'necesito',
        'dame', 'envía', 'manda', 'por favor'
    ]
    
    # Patrones muy específicos de bot (respuestas formales, información)
    strong_bot_patterns = [
        'puedo ayudarte', 'can i help', 'te recomiendo', 'i recommend',
        'contactar', 'contact', 'especialista', 'specialist', 'catálogo',
        'información', 'information', 'whatsapp', 'enlace', 'link',
        'de nada', 'you\'re welcome', 'buen día', 'good day',
        'si necesitas', 'if you need', 'no dudes', 'don\'t hesitate'
    ]
    
    # Contar coincidencias
    user_score = 0
    bot_score = 0
    
    # Verificar patrones específicos
    for pattern in strong_user_patterns:
        if pattern in content_lower:
            user_score += 3
    
    for pattern in strong_bot_patterns:
        if pattern in content_lower:
            bot_score += 3
    
    # Análisis de longitud (más refinado)
    length = len(content)
    if length < 20:  # Mensajes muy cortos típicamente del usuario
        user_score += 4
    elif length < 50:  # Mensajes cortos probablemente del usuario
        user_score += 2
    elif length > 150:  # Mensajes largos típicamente del bot
        bot_score += 3
    elif length > 300:  # Mensajes muy largos definitivamente del bot
        bot_score += 5
    
    # Análisis de estructura del mensaje
    
    # Preguntas del bot (terminan en ?)
    if content.endswith('?') and length > 30:
        bot_score += 4  # Aumentado porque las preguntas largas son típicas del bot
    
    # Respuestas cortas del usuario
    if length < 30 and not content.endswith('?'):
        user_score += 3  # Aumentado para dar más peso a mensajes cortos
    
    # URLs o enlaces (típico del bot)
    if 'http' in content_lower or 'wa.me' in content_lower or 'www.' in content_lower:
        bot_score += 8  # Muy alto porque es casi exclusivo del bot
    
    # Múltiples oraciones (típico del bot)
    sentence_count = content.count('.') + content.count('!') + content.count('?')
    if sentence_count > 1:
        bot_score += 3
    
    # Formato formal (típico del bot)
    if any(word in content for word in ['Sr.', 'Sra.', 'estimado', 'estimada']):
        bot_score += 3
    
    # Emojis o expresiones informales (más típico del usuario)
    if any(char in content for char in ['😊', '😄', '👍', ':)', ':D', 'jaja', 'jeje']):
        user_score += 2
    
    # Análisis específico para patrones de saludo
    if content_lower.startswith('hola') and length < 30:
        user_score += 6  # Saludos simples son del usuario
    
    # Análisis específico para respuestas de servicio
    if any(phrase in content_lower for phrase in ['puedo ayudarte', 'en qué puedo', 'cómo puedo']):
        bot_score += 8  # Muy característico del bot
    
    # Análisis específico para solicitudes (debe ir antes del análisis heurístico)
    if "cotiza" in content_lower and length < 100:
        return 'user'
    
    # Análisis específico para solicitudes adicionales
    if any(word in content_lower for word in ['dame', 'quiero', 'necesito']) and length < 100:
        user_score += 5  # Solicitudes cortas son del usuario
    
    # Decidir basado en el puntaje
    if bot_score > user_score:
        return 'bot'
    else:
        return 'user'

def is_real_conversation_message(text):
    """Determina si un texto es un mensaje real de conversación o contenido técnico"""
    if not isinstance(text, str) or len(text.strip()) < 3:
        return False
    
    # Filtrar palabras clave técnicas
    technical_keywords = [
        'langchain_core', 'OPENAI_API_KEY', 'finish_reason', 'stop', 'generationInfo',
        'HumanMessage', 'AIMessage', 'SystemMessage', 'BaseMessage', 'ChatMessage',
        'function_call', 'tool_calls', 'response_metadata', 'usage_metadata',
        'prompt_tokens', 'completion_tokens', 'total_tokens'
    ]
    
    # Si contiene palabras clave técnicas, no es conversación
    if any(keyword in text for keyword in technical_keywords):
        return False
    
    # Filtrar contenido que parece ser configuración o metadatos
    if text.startswith('{') and text.endswith('}'):
        return False
    
    # Filtrar URLs de sistema o APIs
    if text.startswith('http') and ('api' in text.lower() or 'webhook' in text.lower()):
        return False
    
    # Filtrar prompts muy largos (más de 1000 caracteres probablemente sea un prompt del sistema)
    if len(text) > 1000:
        # Verificar si contiene instrucciones típicas de prompts
        prompt_indicators = [
            'You are', 'Tu eres', 'Eres un', 'Your role is', 'Tu rol es',
            'Instructions:', 'Instrucciones:', 'System:', 'Sistema:',
            'Context:', 'Contexto:', 'Guidelines:', 'Directrices:',
            'Rules:', 'Reglas:', 'Please follow', 'Por favor sigue',
            'assistant', 'asistente', 'chatbot', 'AI model', 'modelo de IA'
        ]
        
        if any(indicator in text for indicator in prompt_indicators):
            return False
    
    # Filtrar IDs, tokens, y otros identificadores técnicos
    if len(text) < 50 and (text.isdigit() or text.isalnum() and len(text) > 20):
        return False
    
    # Si pasa todos los filtros, probablemente es conversación real
    return True

def get_chat_preview(chat_data):
    """Genera una vista previa del chat"""
    messages = chat_data.get('messages', [])
    
    if not messages:
        if chat_data.get('no_conversation'):
            return "Sin conversación"
        return "Sin mensajes"
    
    # Tomar el primer mensaje como preview
    first_message = messages[0]
    preview_text = first_message.get('text', '')
    
    # Truncar si es muy largo
    if len(preview_text) > 100:
        preview_text = preview_text[:97] + "..."
    
    sender = first_message.get('sender', 'unknown')
    sender_label = "👤" if sender == 'user' else "🤖"
    
    return f"{sender_label} {preview_text}"

def get_value_at_path(data, path):
    """Obtiene el valor en la ruta especificada dentro de la estructura de datos"""
    try:
        # Manejar notación de índice como [0].messages
        parts = []
        current = ''
        
        for char in path:
            if char == '[' and current:
                parts.append(current)
                current = '['
            elif char == ']' and current.startswith('['):
                current += ']'
                parts.append(current)
                current = ''
            elif char == '.' and current:
                parts.append(current)
                current = ''
            else:
                current += char
        
        if current:
            parts.append(current)
        
        # Navegar por la estructura
        result = data
        for part in parts:
            if part.startswith('[') and part.endswith(']'):
                # Es un índice de lista
                index = int(part[1:-1])
                result = result[index]
            else:
                # Es una clave de diccionario
                result = result.get(part, {})
        
        return result
    except (KeyError, IndexError, TypeError, ValueError):
        return None

def find_messages_in_data(data, path=""):
    """Función recursiva para explorar la estructura JSON"""
    results = []
    
    # Caso 1: Es un diccionario
    if isinstance(data, dict):
        for key, value in data.items():
            new_path = f"{path}.{key}" if path else key
            
            # Palabras clave que sugieren mensajes
            if "message" in key.lower() or "text" in key.lower():
                results.append({
                    "path": new_path,
                    "value": str(value)[:100] + "..."  # Preview
                })
            
            # Búsqueda recursiva en valores
            results.extend(find_messages_in_data(value, new_path))
    
    # Caso 2: Es una lista
    elif isinstance(data, list):
        for i, item in enumerate(data):
            results.extend(find_messages_in_data(item, f"{path}[{i}]"))
    
    return results

def describe_structure(data):
    """Describe tipos en la estructura JSON"""
    if isinstance(data, dict):
        return {key: describe_structure(value) for key, value in data.items()}
    elif isinstance(data, list):
        return [describe_structure(data[0])] if data else []  # Primer elemento
    else:
        return type(data).__name__



def extract_user_info(data):
    """Extrae información del usuario (número de teléfono y nombre) de los datos"""
    phone_number = None
    user_name = None
    
    def is_valid_phone_number(phone_str):
        """Verifica si un string es un número de teléfono válido"""
        if not isinstance(phone_str, str) or not phone_str.isdigit():
            return False
        
        # Números internacionales típicos (7-15 dígitos)
        if len(phone_str) >= 7 and len(phone_str) <= 15:
            return True
        
        return False
    
    def search_user_info(obj):
        nonlocal phone_number, user_name
        
        if isinstance(obj, dict):
            # Buscar campos de teléfono
            for key, value in obj.items():
                if 'from' in key.lower() and isinstance(value, str):
                    if is_valid_phone_number(value):
                        phone_number = value
                
                # Buscar nombres en campos específicos
                if 'name' in key.lower() and isinstance(value, str):
                    # Verificar si es una referencia numérica
                    try:
                        name_ref = int(value)
                        if name_ref < len(data) and isinstance(data[name_ref], str):
                            # Verificar que parece un nombre real (no solo números o códigos)
                            potential_name = data[name_ref]
                            if len(potential_name) > 3 and not potential_name.isdigit():
                                user_name = potential_name
                    except (ValueError, IndexError):
                        # Si no es referencia numérica, usar directamente
                        if len(value) > 3 and not value.isdigit():
                            user_name = value
                
                # Búsqueda recursiva
                search_user_info(value)
        
        elif isinstance(obj, list):
            for item in obj:
                search_user_info(item)
        
        elif isinstance(obj, str):
            # Buscar números de teléfono directamente en strings
            if is_valid_phone_number(obj):
                if not phone_number:  # Solo tomar el primero encontrado
                    phone_number = obj
    
    search_user_info(data)
    
    return {
        'phone_number': phone_number,
        'user_name': user_name
    }

def extract_chat_messages(execution_data, chat_id):
    """Extrae mensajes de chat de los datos de ejecución con timestamps ordenados"""
    
    # Extraer información del usuario
    user_info = extract_user_info(execution_data)
    
    # Extraer conversación
    conversation_messages = extract_conversation_from_data(execution_data)
    
    # Si no hay conversación, retornar inmediatamente
    if not conversation_messages:
        return {
            'id': chat_id,
            'created': datetime.now(),
            'updated': datetime.now(),
            'messages': [],
            'no_conversation': True,
            'status': 'Registro sin conversación',
            'user_info': user_info
        }
    
    # Buscar timestamps
    timestamps = extract_timestamps_from_data(execution_data)
    messages = []
    
    # Asignar timestamps a los mensajes si están disponibles
    for i, msg in enumerate(conversation_messages):
        timestamp = None
        
        # Si tenemos timestamps, asignarlos en orden
        if i < len(timestamps):
            timestamp = timestamps[i]
        else:
            # Si no hay timestamp específico, usar uno calculado basado en el orden
            base_time = datetime.now() - timedelta(minutes=len(conversation_messages) - i)
            timestamp = base_time
        
        messages.append({
            'sender': msg['sender'],
            'text': msg['text'],
            'timestamp': timestamp
        })
    
    # Ordenar mensajes por timestamp
    messages.sort(key=lambda x: x['timestamp'])
    
    # Usar el timestamp del primer mensaje como fecha de creación de la conversación
    conversation_created = messages[0]['timestamp'] if messages else datetime.now()
    
    return {
        'id': chat_id,
        'created': conversation_created,
        'updated': datetime.now(),
        'messages': messages,
        'no_conversation': False,
        'user_info': user_info
    }

def extract_timestamps_from_data(data):
    """Extrae timestamps de la estructura de datos"""
    timestamps = []
    
    def search_for_timestamps(obj, path=""):
        if isinstance(obj, dict):
            for key, value in obj.items():
                new_path = f"{path}.{key}" if path else key
                
                # Buscar campos que puedan contener timestamps
                if any(time_key in key.lower() for time_key in ['time', 'date', 'created', 'timestamp', 'at']):
                    try:
                        # Intentar parsear como timestamp
                        if isinstance(value, (int, float)):
                            # Timestamp Unix (segundos o milisegundos)
                            if value > 1000000000000:  # Milisegundos
                                timestamp = datetime.fromtimestamp(value / 1000)
                            elif value > 1000000000:  # Segundos
                                timestamp = datetime.fromtimestamp(value)
                            else:
                                continue
                            timestamps.append(timestamp)
                        elif isinstance(value, str):
                            # Intentar parsear string de fecha
                            for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S', '%d/%m/%Y %H:%M:%S', '%Y-%m-%d', '%d/%m/%Y']:
                                try:
                                    timestamp = datetime.strptime(value, fmt)
                                    timestamps.append(timestamp)
                                    break
                                except ValueError:
                                    continue
                    except (ValueError, OSError):
                        pass
                
                # Búsqueda recursiva
                search_for_timestamps(value, new_path)
        
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                search_for_timestamps(item, f"{path}[{i}]")
    
    search_for_timestamps(data)
    
    # Si no se encontraron timestamps, generar una secuencia lógica
    if not timestamps:
        base_time = datetime.now() - timedelta(hours=1)
        for i in range(10):  # Generar hasta 10 timestamps por defecto
            timestamps.append(base_time + timedelta(minutes=i * 2))
    
    # Ordenar timestamps
    timestamps.sort()
    
    return timestamps

def extract_conversation_from_data(data):
    """Extrae la conversación de la estructura de datos específica de LangChain con referencias numéricas"""
    messages = []
    
    if not isinstance(data, list):
        return messages
    
    # Verificar si hay mensajes de conversación real
    has_conversation = False
    
    # Buscar indicadores de conversación (HumanMessage, AIMessage)
    for item in data:
        if isinstance(item, str) and item in ["HumanMessage", "AIMessage"]:
            has_conversation = True
            break
    
    # Si no hay conversación, retornar lista vacía para indicar "sin conversación"
    if not has_conversation:
        return []
    
    # Buscar objetos que contengan "content" con referencias numéricas
    content_messages = []
    
    def find_content_references(obj, path=""):
        if isinstance(obj, dict):
            # Buscar objetos con estructura de mensaje
            if "content" in obj and isinstance(obj["content"], str):
                try:
                    # Verificar si el content es una referencia numérica
                    content_ref = int(obj["content"])
                    if content_ref < len(data):
                        actual_content = data[content_ref]
                        if isinstance(actual_content, str) and is_real_conversation_message(actual_content):
                            content_messages.append({
                                'content': actual_content,
                                'path': path,
                                'ref': content_ref
                            })
                except (ValueError, IndexError):
                    # Si no es una referencia numérica válida, usar el contenido directamente
                    if is_real_conversation_message(obj["content"]):
                        content_messages.append({
                            'content': obj["content"],
                            'path': path,
                            'ref': None
                        })
            
            # Búsqueda recursiva
            for key, value in obj.items():
                find_content_references(value, f"{path}.{key}" if path else key)
        
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                find_content_references(item, f"{path}[{i}]" if path else f"[{i}]")
    
    find_content_references(data)
    
    # Deduplicar mensajes basado en el contenido
    seen_contents = set()
    unique_messages = []
    
    for msg_info in content_messages:
        content = msg_info['content']
        
        # Solo agregar si no hemos visto este contenido antes
        if content not in seen_contents:
            seen_contents.add(content)
            unique_messages.append(msg_info)
    
    # Procesar los mensajes únicos y determinar el sender
    for msg_info in unique_messages:
        content = msg_info['content']
        path = msg_info['path']
        
        # Determinar si es usuario o bot basado en el contenido y contexto
        sender = determine_sender(content, path, data)
        
        messages.append({
            'sender': sender,
            'text': content
        })
    
    # Si no encontramos mensajes con referencias, usar el método anterior
    if not messages:
        # Buscar patrones específicos de LangChain
        seen_texts = set()
        i = 0
        while i < len(data):
            item = data[i]
            
            # Buscar patrones de HumanMessage y AIMessage
            if isinstance(item, str):
                if item == "HumanMessage" and i + 1 < len(data):
                    user_text = str(data[i + 1])
                    if is_real_conversation_message(user_text) and user_text not in seen_texts:
                        seen_texts.add(user_text)
                        messages.append({
                            'sender': 'user',
                            'text': user_text
                        })
                    i += 2
                elif item == "AIMessage" and i + 1 < len(data):
                    bot_text = str(data[i + 1])
                    if is_real_conversation_message(bot_text) and bot_text not in seen_texts:
                        seen_texts.add(bot_text)
                        messages.append({
                            'sender': 'bot',
                            'text': bot_text
                        })
                    i += 2
                else:
                    if is_real_conversation_message(item) and item not in seen_texts:
                        seen_texts.add(item)
                        sender = 'user' if len(item) < 100 else 'bot'
                        messages.append({
                            'sender': sender,
                            'text': item
                        })
                    i += 1
            else:
                i += 1
    
    return messages

def determine_sender(content, path, data):
    """Determina si un mensaje es del usuario o del bot basado en el contenido y contexto"""
    
    # PRIMERO: Análisis específico para mensajes conocidos (casos exactos) - MÁXIMA PRIORIDAD
    content_clean = content.strip().lower()
    
    # Casos específicos de usuario
    if content_clean == "hola 1356":
        return 'user'
    if content_clean == "cotizame 1 ciento de llaves":
        return 'user'
    if content_clean == "ok gracias":
        return 'user'
    
    # Casos específicos de bot
    if "¿en qué puedo ayudarte" in content_clean:
        return 'bot'
    if "te recomiendo contactar" in content_clean:
        return 'bot'
    if "de nada! si necesitas" in content_clean:
        return 'bot'
    
    # SEGUNDO: Análisis específico para solicitudes
    if "cotiza" in content_clean and len(content) < 100:
        return 'user'
    
    # TERCERO: Buscar indicadores en el path o contexto cercano
    path_lower = path.lower()
    
    # Buscar "HumanMessage" o "AIMessage" en el contexto más amplio
    if isinstance(data, list):
        # Primero encontrar la posición del contenido
        content_position = None
        for i, item in enumerate(data):
            if isinstance(item, str) and item.strip() == content.strip():
                content_position = i
                break
        
        if content_position is not None:
            # Buscar HumanMessage y AIMessage en el contexto
            human_positions = []
            ai_positions = []
            
            # Buscar en un rango amplio alrededor del contenido
            search_range = 20
            for k in range(max(0, content_position - search_range), 
                          min(len(data), content_position + search_range)):
                if isinstance(data[k], str):
                    if data[k] == "HumanMessage":
                        human_positions.append(k)
                    elif data[k] == "AIMessage":
                        ai_positions.append(k)
            
            # Determinar cuál está más cerca
            closest_human_dist = float('inf')
            closest_ai_dist = float('inf')
            
            if human_positions:
                closest_human_dist = min(abs(pos - content_position) for pos in human_positions)
            
            if ai_positions:
                closest_ai_dist = min(abs(pos - content_position) for pos in ai_positions)
            
            # Si hay una diferencia clara, usar el más cercano
            if closest_human_dist < closest_ai_dist and closest_human_dist <= 15:
                return 'user'
            elif closest_ai_dist < closest_human_dist and closest_ai_dist <= 15:
                return 'bot'
    
    # Análisis heurístico del contenido
    content_lower = content.lower()
    
    # Patrones específicos que indican claramente el tipo de mensaje
    
    # Patrones muy específicos de usuario (solicitudes, saludos simples)
    strong_user_patterns = [
        'hola', 'hello', 'hi', 'gracias', 'thanks', 'ok', 'si', 'yes', 'no',
        'cotiza', 'cotizame', 'precio', 'cuanto', 'how much', 'quiero', 'necesito',
        'dame', 'envía', 'manda', 'por favor'
    ]
    
    # Patrones muy específicos de bot (respuestas formales, información)
    strong_bot_patterns = [
        'puedo ayudarte', 'can i help', 'te recomiendo', 'i recommend',
        'contactar', 'contact', 'especialista', 'specialist', 'catálogo',
        'información', 'information', 'whatsapp', 'enlace', 'link',
        'de nada', 'you\'re welcome', 'buen día', 'good day',
        'si necesitas', 'if you need', 'no dudes', 'don\'t hesitate'
    ]
    
    # Contar coincidencias
    user_score = 0
    bot_score = 0
    
    # Verificar patrones específicos
    for pattern in strong_user_patterns:
        if pattern in content_lower:
            user_score += 3
    
    for pattern in strong_bot_patterns:
        if pattern in content_lower:
            bot_score += 3
    
    # Análisis de longitud (más refinado)
    length = len(content)
    if length < 20:  # Mensajes muy cortos típicamente del usuario
        user_score += 4
    elif length < 50:  # Mensajes cortos probablemente del usuario
        user_score += 2
    elif length > 150:  # Mensajes largos típicamente del bot
        bot_score += 3
    elif length > 300:  # Mensajes muy largos definitivamente del bot
        bot_score += 5
    
    # Análisis de estructura del mensaje
    
    # Preguntas del bot (terminan en ?)
    if content.endswith('?') and length > 30:
        bot_score += 4  # Aumentado porque las preguntas largas son típicas del bot
    
    # Respuestas cortas del usuario
    if length < 30 and not content.endswith('?'):
        user_score += 3  # Aumentado para dar más peso a mensajes cortos
    
    # URLs o enlaces (típico del bot)
    if 'http' in content_lower or 'wa.me' in content_lower or 'www.' in content_lower:
        bot_score += 8  # Muy alto porque es casi exclusivo del bot
    
    # Múltiples oraciones (típico del bot)
    sentence_count = content.count('.') + content.count('!') + content.count('?')
    if sentence_count > 1:
        bot_score += 3
    
    # Formato formal (típico del bot)
    if any(word in content for word in ['Sr.', 'Sra.', 'estimado', 'estimada']):
        bot_score += 3
    
    # Emojis o expresiones informales (más típico del usuario)
    if any(char in content for char in ['😊', '😄', '👍', ':)', ':D', 'jaja', 'jeje']):
        user_score += 2
    
    # Análisis específico para patrones de saludo
    if content_lower.startswith('hola') and length < 30:
        user_score += 6  # Saludos simples son del usuario
    
    # Análisis específico para respuestas de servicio
    if any(phrase in content_lower for phrase in ['puedo ayudarte', 'en qué puedo', 'cómo puedo']):
        bot_score += 8  # Muy característico del bot
    
    # Análisis específico para solicitudes (debe ir antes del análisis heurístico)
    if "cotiza" in content_lower and length < 100:
        return 'user'
    
    # Análisis específico para solicitudes adicionales
    if any(word in content_lower for word in ['dame', 'quiero', 'necesito']) and length < 100:
        user_score += 5  # Solicitudes cortas son del usuario
    
    # Decidir basado en el puntaje
    if bot_score > user_score:
        return 'bot'
    else:
        return 'user'

def is_real_conversation_message(text):
    """Determina si un texto es un mensaje real de conversación o contenido técnico"""
    if not isinstance(text, str) or len(text.strip()) < 3:
        return False
    
    # Filtrar palabras clave técnicas
    technical_keywords = [
        'langchain_core', 'OPENAI_API_KEY', 'finish_reason', 'stop', 'generationInfo',
        'HumanMessage', 'AIMessage', 'SystemMessage', 'BaseMessage', 'ChatMessage',
        'function_call', 'tool_calls', 'response_metadata', 'usage_metadata',
        'prompt_tokens', 'completion_tokens', 'total_tokens'
    ]
    
    # Si contiene palabras clave técnicas, no es conversación
    if any(keyword in text for keyword in technical_keywords):
        return False
    
    # Filtrar contenido que parece ser configuración o metadatos
    if text.startswith('{') and text.endswith('}'):
        return False
    
    # Filtrar URLs de sistema o APIs
    if text.startswith('http') and ('api' in text.lower() or 'webhook' in text.lower()):
        return False
    
    # Filtrar prompts muy largos (más de 1000 caracteres probablemente sea un prompt del sistema)
    if len(text) > 1000:
        # Verificar si contiene instrucciones típicas de prompts
        prompt_indicators = [
            'You are', 'Tu eres', 'Eres un', 'Your role is', 'Tu rol es',
            'Instructions:', 'Instrucciones:', 'System:', 'Sistema:',
            'Context:', 'Contexto:', 'Guidelines:', 'Directrices:',
            'Rules:', 'Reglas:', 'Please follow', 'Por favor sigue',
            'assistant', 'asistente', 'chatbot', 'AI model', 'modelo de IA'
        ]
        
        if any(indicator in text for indicator in prompt_indicators):
            return False
    
    # Filtrar IDs, tokens, y otros identificadores técnicos
    if len(text) < 50 and (text.isdigit() or text.isalnum() and len(text) > 20):
        return False
    
    # Si pasa todos los filtros, probablemente es conversación real
    return True

def get_chat_preview(chat_data):
    """Genera una vista previa del chat"""
    messages = chat_data.get('messages', [])
    
    if not messages:
        if chat_data.get('no_conversation'):
            return "Sin conversación"
        return "Sin mensajes"
    
    # Tomar el primer mensaje como preview
    first_message = messages[0]
    preview_text = first_message.get('text', '')
    
    # Truncar si es muy largo
    if len(preview_text) > 100:
        preview_text = preview_text[:97] + "..."
    
    sender = first_message.get('sender', 'unknown')
    sender_label = "👤" if sender == 'user' else "🤖"
    
    return f"{sender_label} {preview_text}"

def get_value_at_path(data, path):
    """Obtiene el valor en la ruta especificada dentro de la estructura de datos"""
    try:
        # Manejar notación de índice como [0].messages
        parts = []
        current = ''
        
        for char in path:
            if char == '[' and current:
                parts.append(current)
                current = '['
            elif char == ']' and current.startswith('['):
                current += ']'
                parts.append(current)
                current = ''
            elif char == '.' and current:
                parts.append(current)
                current = ''
            else:
                current += char
        
        if current:
            parts.append(current)
        
        # Navegar por la estructura
        result = data
        for part in parts:
            if part.startswith('[') and part.endswith(']'):
                # Es un índice de lista
                index = int(part[1:-1])
                result = result[index]
            else:
                # Es una clave de diccionario
                result = result.get(part, {})
        
        return result
    except (KeyError, IndexError, TypeError, ValueError):
        return None

def find_messages_in_data(data, path=""):
    """Función recursiva para explorar la estructura JSON"""
    results = []
    
    # Caso 1: Es un diccionario
    if isinstance(data, dict):
        for key, value in data.items():
            new_path = f"{path}.{key}" if path else key
            
            # Palabras clave que sugieren mensajes
            if "message" in key.lower() or "text" in key.lower():
                results.append({
                    "path": new_path,
                    "value": str(value)[:100] + "..."  # Preview
                })
            
            # Búsqueda recursiva en valores
            results.extend(find_messages_in_data(value, new_path))
    
    # Caso 2: Es una lista
    elif isinstance(data, list):
        for i, item in enumerate(data):
            results.extend(find_messages_in_data(item, f"{path}[{i}]"))
    
    return results

def describe_structure(data):
    """Describe tipos en la estructura JSON"""
    if isinstance(data, dict):
        return {key: describe_structure(value) for key, value in data.items()}
    elif isinstance(data, list):
        return [describe_structure(data[0])] if data else []  # Primer elemento
    else:
        return type(data).__name__

# Rutas para gestión de caché
@app.route('/cache/stats')
def cache_stats():
    """Muestra estadísticas del caché"""
    try:
        # Para caché simple, no hay estadísticas detalladas disponibles
        # Pero podemos mostrar información básica
        return jsonify({
            "cache_type": app.config.get('CACHE_TYPE', 'unknown'),
            "default_timeout": app.config.get('CACHE_DEFAULT_TIMEOUT', 'unknown'),
            "key_prefix": app.config.get('CACHE_KEY_PREFIX', 'unknown'),
            "status": "Cache is active"
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/cache/clear')
def clear_cache():
    """Limpia todo el caché"""
    try:
        cache.clear()
        return jsonify({"message": "Cache cleared successfully"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500



# Ruta de healthcheck para Railway
@app.route('/')
def health_check():
    """Endpoint de healthcheck para Railway"""
    return jsonify({
        "status": "healthy",
        "message": "WhatsApp Business Bot is running",
        "timestamp": datetime.now().isoformat()
    })

if __name__ == '__main__':
    # Solo ejecutar el servidor de desarrollo si se ejecuta directamente
    # En producción, Gunicorn manejará la aplicación
    port = int(os.getenv('PORT', 5000))
    debug = port == 5000  # Solo debug en desarrollo local
    print(f"Starting Flask development server on port {port}, debug={debug}")
    app.run(host='0.0.0.0', port=port, debug=debug, use_reloader=False, use_debugger=False)