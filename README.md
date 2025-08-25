# 🤖 Agent Conversation - WhatsApp Business Bot

Sistema de agente conversacional inteligente para WhatsApp Business API que permite gestionar conversaciones automatizadas con menús interactivos y categorización de servicios.

## 🚀 Características

- **Menús Interactivos**: Sistema de menús dinámicos con 8 categorías de productos/servicios
- **Gestión de Sesiones**: Control automático de sesiones con expiración de 5 minutos
- **Routing Inteligente**: Detección robusta de opciones por número, texto y emojis
- **Interfaz Web**: Panel de administración para gestión de conversaciones
- **Base de Datos**: Integración con PostgreSQL para persistencia de datos
- **API REST**: Endpoints para integración con WhatsApp Business API

## 📋 Categorías de Servicios

1. **⛽ Gas Natural** - Productos y servicios de gas natural
2. **🚗 Automotriz** - Repuestos y accesorios automotrices
3. **🏗️ Construcción** - Materiales de construcción
4. **🔥 Gas Licuado (GLP)** - Cilindros y accesorios GLP
5. **🔧 Mangueras y Conexiones** - Mangueras y conexiones de bronce
6. **🔩 Bronce, Latón y Llaves** - Accesorios de bronce y latón
7. **🏭 Servicios Industriales** - Servicios para industrias
8. **❓ Otro** - Consultas generales

## 🛠️ Tecnologías

- **Backend**: Flask (Python)
- **Base de Datos**: PostgreSQL (Railway)
- **Frontend**: HTML, CSS, JavaScript
- **API**: WhatsApp Business API
- **Deployment**: Railway

## 📦 Instalación

### Prerrequisitos
- Python 3.8+
- PostgreSQL
- Cuenta de WhatsApp Business API

### Pasos de Instalación

1. **Clonar el repositorio**
   ```bash
   git clone https://github.com/tu-usuario/agent-conversation.git
   cd agent-conversation
   ```

2. **Crear entorno virtual**
   ```bash
   python -m venv venv
   source venv/bin/activate  # En Windows: venv\Scripts\activate
   ```

3. **Instalar dependencias**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configurar variables de entorno**
   ```bash
   cp .env.example .env
   # Editar .env con tus credenciales
   ```

5. **Ejecutar la aplicación**
   ```bash
   python app.py
   ```

## ⚙️ Configuración

### Variables de Entorno (.env)

```env
FLASK_APP=app.py
FLASK_ENV=development

# Configuración de Base de Datos
# IMPORTANTE: Railway optimizado para evitar cargos de egress
DATABASE_URL=postgresql://usuario:password@host:puerto/database

# Variables individuales (fallback)
DB_HOST=localhost
DB_PORT=5432
DB_NAME=railway
DB_USER=postgres
DB_PASSWORD=tu_password

# WhatsApp Business API
WHATSAPP_TOKEN=tu_whatsapp_token
WHATSAPP_VERIFY_TOKEN=tu_verify_token
WHATSAPP_PHONE_NUMBER_ID=tu_phone_number_id
```

### 🚂 Optimización para Railway

**⚠️ IMPORTANTE:** Para evitar cargos extra de egress en Railway:

- **Conexión Privada:** Railway automáticamente proporciona `DATABASE_URL` con dominio privado
- **Sin Cargos de Egress:** Las conexiones internas no generan costos adicionales
- **Variables Automáticas:** Railway configura automáticamente las variables de entorno necesarias

**En producción Railway:**
```env
# Railway proporciona automáticamente:
DATABASE_URL=postgresql://postgres:password@railway-internal-domain:5432/railway
RAILWAY_PRIVATE_DOMAIN=internal-domain.railway.internal
```

**Configuración incluida:**
- `railway.json` - Configuración específica de despliegue
- Variables de entorno optimizadas
- Conexión de base de datos privada

## 🚀 Uso

### Interfaz Web
Accede a `http://localhost:5000` para:
- Ver lista de conversaciones
- Gestionar chats activos
- Monitorear el sistema

### API Endpoints
- `GET /` - Página principal
- `POST /webhook` - Webhook para WhatsApp
- `GET /webhook` - Verificación de webhook
- `GET /chats` - Lista de conversaciones
- `GET /chat/<phone_number>` - Chat específico

## 📁 Estructura del Proyecto

```
agent-conversation/
├── app.py              # Aplicación Flask principal
├── menu.json           # Configuración del menú interactivo
├── norm.js             # Lógica de normalización y routing
├── rag.json            # Configuración RAG
├── requirements.txt    # Dependencias Python
├── .env               # Variables de entorno
├── .gitignore         # Archivos ignorados por Git
└── templates/         # Plantillas HTML
    ├── chat_list.html
    ├── chats.html
    └── login.html
```

## 🔄 Flujo de Conversación

1. **Primer Contacto**: Usuario envía mensaje inicial
2. **Menú Principal**: Sistema muestra menú con 8 opciones
3. **Selección**: Usuario elige opción (número, texto o emoji)
4. **Routing**: Sistema dirige a agente especializado
5. **Conversación**: Interacción con agente específico
6. **Expiración**: Sesión expira después de 5 minutos de inactividad

## 🛡️ Características de Seguridad

- Validación de tokens de WhatsApp
- Sanitización de inputs
- Control de sesiones
- Variables de entorno para credenciales

## 🚀 Deployment

### Railway (Recomendado)

1. Conectar repositorio a Railway
2. Configurar variables de entorno
3. Deploy automático desde main branch

### Docker (Opcional)

```dockerfile
FROM python:3.9-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
EXPOSE 5000
CMD ["python", "app.py"]
```

## 🤝 Contribución

1. Fork el proyecto
2. Crea una rama para tu feature (`git checkout -b feature/AmazingFeature`)
3. Commit tus cambios (`git commit -m 'Add some AmazingFeature'`)
4. Push a la rama (`git push origin feature/AmazingFeature`)
5. Abre un Pull Request

## 📝 Licencia

Este proyecto está bajo la Licencia MIT - ver el archivo [LICENSE](LICENSE) para detalles.

## 📞 Soporte

Para soporte técnico o consultas:
- 📧 Email: soporte@tuempresa.com
- 💬 WhatsApp: +1234567890
- 🐛 Issues: [GitHub Issues](https://github.com/tu-usuario/agent-conversation/issues)

## 🔄 Changelog

### v1.0.0 (2025-08-25)
- ✅ Sistema de menús interactivos implementado
- ✅ Routing inteligente con detección múltiple
- ✅ Gestión de sesiones con expiración automática
- ✅ Integración completa con WhatsApp Business API
- ✅ Panel de administración web
- ✅ Base de datos PostgreSQL integrada