// Normalize user message for AI Agent with persistent agent selection and session expiration
const out = [];

for (const item of items) {
  const j = item.json || {};
  let text = '';

  // Inicializar datos del workflow
  const wfData = $getWorkflowStaticData('node');
  if (!wfData.seenMenu) wfData.seenMenu = {};
  if (!wfData.selectedAgent) wfData.selectedAgent = {};
  if (!wfData.lastInteraction) wfData.lastInteraction = {};
  
  const from = j._from_normalized || j.from || (j.messages && j.messages[0] && j.messages[0].from);
  
  // Verificar expiración de sesión (5 minutos = 300,000 ms)
  const now = Date.now();
  const lastInteraction = wfData.lastInteraction[from] || 0;
  const sessionExpired = (now - lastInteraction) > 300000; // 5 minutos
  
  // Si la sesión expiró, limpiar datos del usuario
  if (sessionExpired && from) {
    delete wfData.seenMenu[from];
    delete wfData.selectedAgent[from];
  }
  
  // Actualizar timestamp de última interacción
  if (from) {
    wfData.lastInteraction[from] = now;
  }
  
  const isFirstContact = from ? !wfData.seenMenu[from] : false;
  const hasSelectedAgent = from ? wfData.selectedAgent[from] : null;
  
  // Si es el primer contacto (o sesión expirada), marcar como visto y enviar menú
  if (isFirstContact && from) {
    wfData.seenMenu[from] = true;
    item.json.sendMenu = true;
    item.json.userMessage = 'FIRST_CONTACT';
    item.json.routeTo = 'FIRST_CONTACT';
    out.push(item);
    continue;
  }

  // Extraer el mensaje del usuario
  if (j.selection && j.selection.mappedText) {
    text = j.selection.mappedText;
  } else if (j.messages && j.messages[0]) {
    const m = j.messages[0];
    if (m.text && m.text.body) {
      text = m.text.body;
    } else if (m.interactive && m.interactive.list_reply) {
      text = m.interactive.list_reply.title || m.interactive.list_reply.id || '';
    } else if (m.button && m.button.text) {
      text = m.button.text;
    } else {
      text = j.body || '';
    }
  } else if (j.userMessage) {
    text = j.userMessage;
  } else if (j.text && j.text.body) {
    text = j.text.body;
  } else {
    text = '';
  }

  // Detectar comando para regresar al menú
  if (from && (text.toLowerCase() === 'menú' || text.toLowerCase() === 'menu')) {
    delete wfData.selectedAgent[from];
    item.json.userMessage = 'FIRST_CONTACT';
    item.json.routeTo = 'FIRST_CONTACT';
  }
  // Detectar y guardar selección de agente según las 8 opciones
  else if (from && (text === '1' || text.toLowerCase().includes('gas natural') || text.includes('🔥'))) {
    wfData.selectedAgent[from] = 'gas_natural';
    item.json.userMessage = text;
    item.json.routeTo = 'gas_natural';
  }
  else if (from && (text === '2' || text.toLowerCase().includes('automotriz') || text.includes('🚗'))) {
    wfData.selectedAgent[from] = 'automotriz';
    item.json.userMessage = text;
    item.json.routeTo = 'automotriz';
  }
  else if (from && (text === '3' || text.toLowerCase().includes('construcción') || text.includes('🏗️'))) {
    wfData.selectedAgent[from] = 'construccion';
    item.json.userMessage = text;
    item.json.routeTo = 'construccion';
  }
  else if (from && (text === '4' || text.toLowerCase().includes('glp') || text.toLowerCase().includes('gas licuado') || text.includes('🛢️'))) {
    wfData.selectedAgent[from] = 'glp';
    item.json.userMessage = text;
    item.json.routeTo = 'glp';
  }
  else if (from && (text === '5' || text.toLowerCase().includes('mangueras') || text.toLowerCase().includes('conexiones') || text.includes('🔧'))) {
    wfData.selectedAgent[from] = 'conexiones';
    item.json.userMessage = text;
    item.json.routeTo = 'conexiones';
  }
  else if (from && (text === '6' || text.toLowerCase().includes('bronce') || text.toLowerCase().includes('laton') || text.toLowerCase().includes('llaves') || text.includes('🔑'))) {
    wfData.selectedAgent[from] = 'laton_llaves';
    item.json.userMessage = text;
    item.json.routeTo = 'laton_llaves';
  }
  else if (from && (text === '7' || text.toLowerCase().includes('servicios industriales') || text.includes('⚙️'))) {
    wfData.selectedAgent[from] = 'servicios';
    item.json.userMessage = text;
    item.json.routeTo = 'servicios';
  }
  else if (from && (text === '8' || text.toLowerCase().includes('otro') || text.includes('❓'))) {
    wfData.selectedAgent[from] = 'otro';
    item.json.userMessage = text;
    item.json.routeTo = 'otro';
  }
  // Si ya tiene un agente seleccionado, usar ese agente
  else if (hasSelectedAgent && from) {
    item.json.userMessage = text;
    item.json.routeTo = hasSelectedAgent;
  }
  // Si no tiene agente seleccionado y no es selección válida, ir a fallback
  else {
    item.json.userMessage = text;
    item.json.routeTo = 'fallback';
  }

  out.push(item);
}

return out;
