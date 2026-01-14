import streamlit as st
from github import Github, GithubException
import json
import pandas as pd
from datetime import datetime, date, timedelta
import calendar

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(
    page_title="Academic Task Planner",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- CONFIGURACIÓN DE USUARIO (CAMBIAR ESTO) ---
# Nombre del repositorio donde se guardará el archivo tareas.json
REPO_NAME = "MrCordobex/Personal-project"  # <-- ¡ACTUALIZA ESTO CON TU REPO!
FILE_PATH = "tareas.json"

# --- ESTRUCTURA DE HORARIO FIJO (Editable) ---
# Adapta esto con tus asignaturas reales
HORARIO_FIJO = {
    0: [ # Lunes
        {"hora": "09:00 - 11:00", "asignatura": "Desarrollo Web", "aula": "1.4"},
        {"hora": "11:30 - 13:30", "asignatura": "Bases de Datos", "aula": "2.1"},
    ],
    1: [ # Martes
        {"hora": "09:00 - 11:00", "asignatura": "Inteligencia Artificial", "aula": "1.4"},
    ],
    2: [ # Miércoles
        {"hora": "10:00 - 12:00", "asignatura": "Redes de Computadores", "aula": "Lab 3"},
    ],
    3: [ # Jueves
        {"hora": "09:00 - 11:00", "asignatura": "Desarrollo Web", "aula": "1.4"},
        {"hora": "15:00 - 17:00", "asignatura": "Ingeniería Software", "aula": "2.2"},
    ],
    4: [ # Viernes
        {"hora": "09:00 - 11:00", "asignatura": "Inglés Técnico", "aula": "Online"},
    ],
    5: [], # Sábado
    6: []  # Domingo
}

COLORES_PRIORIDAD = {
    "Importante": "orange",
    "Urgente": "red",
    "Normal": "green"
}

COLORES_TIPO = {
    "Examen": "#FF4B4B",     # Rojo vivo
    "Entrega": "#FFA500",    # Naranja
    "Estudio": "#1E90FF",    # Azul
    "Lectura": "#9370DB",    # Morado
    "Otro": "#808080",       # Gris
    "Clase": "#2E8B57"       # Verde mar (para el horario)
}

# --- GESTIÓN DE PERSISTENCIA (GITHUB) ---

def obtener_conexion_repo():
    """Conecta con la API de GitHub usando el token almacenado en secrets."""
    try:
        if "GITHUB_TOKEN" not in st.secrets:
            st.error("❌ Falta el Token en Secrets (.streamlit/secrets.toml).")
            return None
        
        token = st.secrets["GITHUB_TOKEN"]
        g = Github(token)
        return g.get_repo(REPO_NAME)
    except Exception as e:
        st.error(f"Error conectando a GitHub: {e}")
        return None

def gestionar_tareas(accion, nueva_tarea=None, id_tarea_eliminar=None, tarea_actualizada=None, lista_completa=None):
    """
    Gestiona el CRUD de tareas en el archivo JSON de GitHub.
    accion: 'leer', 'crear', 'borrar', 'actualizar', 'guardar_todo'
    """
    repo = obtener_conexion_repo()
    if not repo:
        return [] if accion == 'leer' else False

    try:
        # Intentar leer el archivo existente
        try:
            contents = repo.get_contents(FILE_PATH)
            datos = json.loads(contents.decoded_content.decode())
        except GithubException:
            # Si no existe, inicializamos lista vacía create_file luego
            datos = []
            contents = None

        if accion == 'leer':
            return datos

        elif accion == 'crear' and nueva_tarea:
            datos.append(nueva_tarea)
            mensaje = f"Nueva tarea: {nueva_tarea['titulo']}"
        
        elif accion == 'borrar' and id_tarea_eliminar is not None:
            datos = [t for t in datos if t.get('id') != id_tarea_eliminar]
            mensaje = f"Borrar tarea ID: {id_tarea_eliminar}"

        elif accion == 'actualizar' and tarea_actualizada:
            # Reemplazar la tarea con el mismo ID
            datos = [t if t.get('id') != tarea_actualizada['id'] else tarea_actualizada for t in datos]
            mensaje = f"Actualizar tarea: {tarea_actualizada['titulo']}"
            
        elif accion == 'guardar_todo' and lista_completa is not None:
            datos = lista_completa
            mensaje = "Limpieza automática de tareas antiguas"
        
        else:
            return False

        # Guardar cambios
        json_content = json.dumps(datos, indent=4)
        if contents:
            repo.update_file(contents.path, mensaje, json_content, contents.sha)
        else:
            repo.create_file(FILE_PATH, "Inicializar tareas.json", json_content)
        
        return True

    except Exception as e:
        st.error(f"Error operando en GitHub ({accion}): {e}")
        return False

# --- UI Y LÓGICA ---

def main():
    st.title("🎓 Academic Task Planner")

    # --- NOTIFICACIONES GLOBLALES ---
    if "mensaje_global" in st.session_state and st.session_state["mensaje_global"]:
        tipo = st.session_state["mensaje_global"]["tipo"]
        texto = st.session_state["mensaje_global"]["texto"]
        if tipo == "exito":
            st.success(texto)
        elif tipo == "error":
            st.error(texto)
        st.session_state["mensaje_global"] = None
        
    # Cargar datos
    tareas = gestionar_tareas('leer')
    
    # --- LIMPIEZA AUTOMÁTICA ---
    hoy_real = date.today()
    tareas_filtradas = []
    hubo_cambios_limpieza = False
    
    for t in tareas:
        fecha_ref_str = t.get('fecha_fin') if t.get('fecha_fin') else t.get('fecha')
        try:
            fecha_ref = datetime.strptime(fecha_ref_str, "%Y-%m-%d").date()
            if fecha_ref >= hoy_real:
                tareas_filtradas.append(t)
            else:
                hubo_cambios_limpieza = True
        except:
            tareas_filtradas.append(t)
            
    if hubo_cambios_limpieza:
        if gestionar_tareas('guardar_todo', lista_completa=tareas_filtradas):
            st.toast("🧹 Se han eliminado tareas antiguas automáticamente.")
            tareas = tareas_filtradas

    # --- SIDEBAR GLOBAL ---
    with st.sidebar:
        st.header("👁️ Navegación")
        # Menú ampliado
        opciones_navegacion = ["Diaria", "Semanal", "Mensual", "---", "➕ Nueva Tarea", "📋 Gestionar Todas"]
        vista_actual = st.radio("Ir a:", opciones_navegacion, index=0, label_visibility="collapsed")
        
        st.divider()
        st.header("📅 Control de Fecha")
        fecha_seleccionada = st.date_input("Fecha Base", date.today())
        st.info(f"Mirando: **{fecha_seleccionada.strftime('%d %b')}**")

    # --- ENRUTADOR DE VISTAS ---
    if vista_actual == "Diaria":
        render_vista_diaria(tareas, fecha_seleccionada)
    elif vista_actual == "Semanal":
        render_vista_semanal(tareas, fecha_seleccionada)
    elif vista_actual == "Mensual":
        render_vista_mensual(tareas, fecha_seleccionada)
    elif vista_actual == "➕ Nueva Tarea":
        render_vista_nueva_tarea()
    elif vista_actual == "📋 Gestionar Todas":
        render_vista_gestionar_todas(tareas)

# --- IMPLEMENTACIÓN DE VISTAS ---

def render_vista_nueva_tarea():
    st.subheader("➕ Añadir Nueva Tarea")
    
    with st.container(border=True):
        col_tipo, col_form = st.columns([1, 3])
        
        with col_tipo:
            st.info("Configuración Básica")
            modo_tarea = st.radio("Modo de Tarea", ["📅 Día concreto", "⏰ Deadline"])
            
        with col_form:
            with st.form("form_nueva_tarea_main"):
                tit = st.text_input("Título de la tarea")
                
                c1, c2 = st.columns(2)
                if "Deadline" in modo_tarea:
                    f_fin = c1.date_input("Fecha Límite (Deadline)", date.today())
                    f_ini = None
                else:
                    f_ini = c1.date_input("Fecha de Realización", date.today())
                    f_fin = None
                    
                prio = c2.selectbox("Prioridad", ["Normal", "Importante", "Urgente"])
                
                c3, c4 = st.columns(2)
                tipo = c3.selectbox("Tipo / Asignatura", list(COLORES_TIPO.keys())[:-1]) # Excluir 'Clase'
                
                st.write("") # Espacio
                if st.form_submit_button("💾 Guardar Tarea", use_container_width=True, type="primary"):
                    nt = {
                        "id": int(datetime.now().timestamp()), 
                        "titulo": tit, 
                        "prioridad": prio, 
                        "tipo": tipo, 
                        "estado": "Pendiente", 
                        "fecha": str(f_ini) if f_ini else str(date.today()), 
                        "fecha_fin": str(f_fin) if f_fin else None
                    }
                    gestionar_tareas('crear', nueva_tarea=nt)
                    st.session_state["mensaje_global"] = {"tipo": "exito", "texto": "💾 Tarea creada correctamente"}
                    st.rerun()

def render_vista_gestionar_todas(tareas):
    st.subheader("📋 Gestión Global de Tareas")
    
    if not tareas:
        st.info("No hay tareas registradas. ¡Añade una nueva!")
        return

    # Filtros simples (opcional para el futuro, por ahora listado limpio)
    
    # Grid de tareas
    for t in tareas:
        # Icono y Color
        estado_icon = "✅" if t['estado'] == 'Completada' else "⬜"
        color_borde = COLORES_PRIORIDAD.get(t.get('prioridad', 'Normal'), "gray")
        bg_opacity = "0.5" if t['estado'] == 'Completada' else "1"
        
        with st.container(border=True):
            c_main, c_actions = st.columns([5, 1])
            
            with c_main:
                # Título grande
                st.markdown(f"<h4 style='margin:0; opacity:{bg_opacity}'>{estado_icon} {t['titulo']}</h4>", unsafe_allow_html=True)
                
                # Metadatos en linea
                f_texto = f"📅 {t['fecha']}" if t.get('fecha') else f"⏰ Deadline: {t['fecha_fin']}"
                st.caption(f"{t['tipo']} | {t['prioridad']} | {f_texto}")
                
            with c_actions:
                # Botón expander para editar
                with st.popover("✏️ Editar"):
                    with st.form(f"edit_main_{t['id']}"):
                        e_titulo = st.text_input("Título", t['titulo'])
                        
                        es_deadline = t.get('fecha_fin') is not None
                        if es_deadline:
                            fecha_act = datetime.strptime(t['fecha_fin'], "%Y-%m-%d").date()
                            e_fecha = st.date_input("Deadline", fecha_act)
                        else:
                            fecha_act = datetime.strptime(t['fecha'], "%Y-%m-%d").date()
                            e_fecha = st.date_input("Fecha", fecha_act)

                        e_estado = st.selectbox("Estado", ["Pendiente", "Completada"], index=0 if t['estado']=="Pendiente" else 1)
                        e_prioridad = st.selectbox("Prioridad", ["Normal", "Importante", "Urgente"], index=["Normal", "Importante", "Urgente"].index(t.get('prioridad', 'Normal')))
                        
                        if st.form_submit_button("Guardar Cambios"):
                            t['titulo'] = e_titulo
                            t['estado'] = e_estado
                            t['prioridad'] = e_prioridad
                            if es_deadline: t['fecha_fin'] = str(e_fecha)
                            else: t['fecha'] = str(e_fecha)
                            gestionar_tareas('actualizar', tarea_actualizada=t)
                            st.session_state["mensaje_global"] = {"tipo": "exito", "texto": "✏️ Tarea actualizada"}
                            st.rerun()
                            
                if st.button("🗑️", key=f"del_main_{t['id']}", help="Borrar tarea"):
                    gestionar_tareas('borrar', id_tarea_eliminar=t['id'])
                    st.session_state["mensaje_global"] = {"tipo": "exito", "texto": "🗑️ Tarea eliminada"}
                    st.rerun()


def render_vista_diaria(tareas, fecha_seleccionada):
    col_horario, col_tareas = st.columns([1, 2])
    
    with col_horario:
        st.subheader("🏫 Horario")
        dia_semana = fecha_seleccionada.weekday()
        clases_hoy = HORARIO_FIJO.get(dia_semana, [])
        if clases_hoy:
            for clase in clases_hoy:
                st.success(f"**{clase['hora']}**\n\n{clase['asignatura']}\n\n📍 {clase['aula']}")
        else:
            st.info("No hay clases programadas.")
    
    with col_tareas:
        st.subheader(f"📝 Tareas: {fecha_seleccionada.strftime('%A %d')}")
        
        tareas_hoy_list = []
        tareas_proximas_list = []
        hoy_real = date.today()

        for t in tareas:
            if t.get('estado') == 'Completada' and t.get('fecha') != str(fecha_seleccionada) and t.get('fecha_fin') != str(fecha_seleccionada):
                    continue 

            es_task_deadline = t.get('fecha_fin') is not None
            
            # Urgencia
            es_urgente_auto = False
            dias_restantes_msg = ""
            if es_task_deadline:
                try:
                    d_fin = datetime.strptime(t['fecha_fin'], "%Y-%m-%d").date()
                    delta_dias = (d_fin - hoy_real).days
                    if delta_dias < 2 and delta_dias >= 0: es_urgente_auto = True
                    if delta_dias < 0: dias_restantes_msg = f"🔴 Venció"
                    elif delta_dias == 0: dias_restantes_msg = "🟠 Vence HOY"
                    else: dias_restantes_msg = f"⏳ {delta_dias}d"
                except: pass
            
            t_visual = t.copy()
            t_visual['msg'] = dias_restantes_msg
            t_visual['urgente'] = es_urgente_auto
            
            if not es_task_deadline and t.get('fecha') == str(fecha_seleccionada):
                tareas_hoy_list.append(t_visual)
            elif es_task_deadline and fecha_seleccionada == hoy_real:
                tareas_proximas_list.append(t_visual)

        if not tareas_hoy_list and not tareas_proximas_list:
            st.info("✅ Nada pendiente para hoy.")

        if tareas_hoy_list:
            st.markdown("### 📅 Tareas del Día")
            for t in tareas_hoy_list:
                color = COLORES_TIPO.get(t['tipo'], "gray")
                estilo_completada = "opacity: 0.5;" if t['estado'] == 'Completada' else ""
                
                with st.container(border=True):
                        c1, c2 = st.columns([4, 1])
                        c1.markdown(f"<div style='{estilo_completada}'><strong>{t['titulo']}</strong> <span style='background-color:{color}; padding: 2px 6px; border-radius: 4px; color: white; font-size: 0.8em'>{t['tipo']}</span></div>", unsafe_allow_html=True)
                        if t['estado'] != 'Completada':
                            if c2.button("✅", key=f"d_{t['id']}"):
                                t['estado'] = 'Completada'
                                gestionar_tareas('actualizar', tarea_actualizada=t)
                                st.rerun()
                        else:
                            c2.write("✅")

        if tareas_proximas_list and fecha_seleccionada == hoy_real:
            st.markdown("### 🚑 Entregas y Deadlines")
            for t in tareas_proximas_list:
                color = COLORES_TIPO.get(t['tipo'], "gray")
                urgency_icon = "🔥" if t['urgente'] else "⏰"
                estilo_completada = "opacity: 0.5;" if t['estado'] == 'Completada' else ""
                
                with st.container(border=True):
                        c1, c2 = st.columns([4, 1])
                        c1.markdown(f"<div style='{estilo_completada}'>{urgency_icon} <strong>{t['titulo']}</strong> | {t['msg']}</div>", unsafe_allow_html=True) 
                        c1.caption(f"Tipo: {t['tipo']}")
                        if t['estado'] != 'Completada':
                            if c2.button("✅", key=f"d_p_{t['id']}"):
                                t['estado'] = 'Completada'
                                gestionar_tareas('actualizar', tarea_actualizada=t)
                                st.rerun()
                        else:
                            c2.write("✅")

def render_vista_semanal(tareas, fecha_base):
    st.subheader(f"Vista Semanal")
    
    start_of_week = fecha_base - timedelta(days=fecha_base.weekday())
    
    cols = st.columns(7)
    dias_semana = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
    
    for i, col in enumerate(cols):
        dia_actual = start_of_week + timedelta(days=i)
        is_today = dia_actual == date.today()
        header_style = "border-bottom: 3px solid red;" if is_today else "border-bottom: 1px solid #444;"
        
        with col:
            st.markdown(f"<div style='text-align: center; {header_style} margin-bottom:5px;'><strong>{dias_semana[i]}</strong><br><span style='font-size:1.2em'>{dia_actual.day}</span></div>", unsafe_allow_html=True)
            
            # 1. Horario
            clases = HORARIO_FIJO.get(i, [])
            for c in clases:
                st.markdown(f"<div style='background-color: {COLORES_TIPO['Clase']}; color: white; padding: 4px; border-radius: 4px; margin: 2px 0; font-size: 0.7em'>🏫 {c['asignatura']}</div>", unsafe_allow_html=True)
            
            # 2. Tareas
            for t in tareas:
                if t.get('estado') == 'Completada': continue
                
                fecha_t = t.get('fecha')
                fecha_f = t.get('fecha_fin')
                
                if fecha_t == str(dia_actual) and not fecha_f:
                    color = COLORES_TIPO.get(t.get('tipo'), "gray")
                    st.markdown(f"<div style='background-color: {color}; color: white; padding: 4px; border-radius: 4px; margin: 2px 0; font-size: 0.7em'>📅 {t['titulo']}</div>", unsafe_allow_html=True)
                
                if fecha_f == str(dia_actual):
                    color = COLORES_TIPO.get(t.get('tipo'), "gray")
                    st.markdown(f"<div style='border: 2px solid {color}; color: white; padding: 3px; border-radius: 4px; margin: 2px 0; font-size: 0.7em'>⏰ {t['titulo']}</div>", unsafe_allow_html=True)

# --- CONSTANTES DE FECHA (ESPAÑOL) ---
NOMBRES_MESES = {
    1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril", 5: "Mayo", 6: "Junio",
    7: "Julio", 8: "Agosto", 9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre"
}
DIAS_SEMANA_ABR = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]

def render_vista_mensual(tareas, fecha_base):
    nombre_mes = NOMBRES_MESES.get(fecha_base.month, "Mes")
    st.subheader(f"Vista Mensual - {nombre_mes} {fecha_base.year}")
    
    # Asegurar Lunes como primer día
    calendar.setfirstweekday(calendar.MONDAY)
    cal = calendar.monthcalendar(fecha_base.year, fecha_base.month)
    
    # Cabecera
    cols_header = st.columns(7)
    for i, d in enumerate(DIAS_SEMANA_ABR):
        cols_header[i].markdown(f"<div style='text-align:center; background-color: #262730; padding: 5px; border-radius: 4px; margin-bottom: 5px;'><strong>{d}</strong></div>", unsafe_allow_html=True)
        
    for week in cal:
        cols = st.columns(7)
        for i, day_num in enumerate(week):
            with cols[i]:
                # Si el día es 0 (mes anterior/siguiente), ocultar completamente
                if day_num == 0:
                    st.markdown("<div style='min-height:100px;'></div>", unsafe_allow_html=True)
                    continue
                
                dia_actual = date(fecha_base.year, fecha_base.month, day_num)
                is_today = dia_actual == date.today()
                
                # Definir colores y bordes
                bg_color = "transparent"
                border_color = "#ff4b4b" if is_today else "#333" 
                border_width = "2px" if is_today else "1px"
                
                # --- CONSTRUCCIÓN DEL HTML DE LA CELDA ---
                html_celda = f"""
                <div style='
                    min-height: 120px;
                    border: {border_width} solid {border_color};
                    background-color: {bg_color};
                    border-radius: 6px;
                    padding: 4px;
                    margin-bottom: 4px;
                    display: flex;
                    flex-direction: column;
                '>
                """
                
                # 1. HEADER (Número)
                color_num = "#ff4b4b" if is_today else "#ccc"
                html_celda += f"""
                <div style='
                    text-align: right; 
                    font-weight: bold; 
                    color: {color_num};
                    border-bottom: 1px solid #333;
                    margin-bottom: 4px;
                    padding-bottom: 2px;
                '>{day_num}</div>
                """
                
                # 2. CONTENIDO (Horario + Tareas)
                
                # Horario
                clases = HORARIO_FIJO.get(i, [])
                for c in clases:
                    html_celda += f"<div style='background-color: {COLORES_TIPO['Clase']}; color: white; padding: 2px 4px; border-radius: 3px; margin-bottom: 2px; font-size: 0.7em; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;'>🏫 {c['asignatura']}</div>"
                
                # Tareas
                for t in tareas:
                    if t.get('estado') == 'Completada': continue
                    fecha_t = t.get('fecha')
                    fecha_f = t.get('fecha_fin')
                    
                    titulo_corto = (t['titulo'][:12] + '..') if len(t['titulo']) > 12 else t['titulo']
                    
                    # Tarea de Día
                    if fecha_t == str(dia_actual) and not fecha_f:
                        color = COLORES_TIPO.get(t.get('tipo'), "gray")
                        html_celda += f"<div style='background-color: {color}; color: white; padding: 2px 4px; border-radius: 3px; margin-bottom: 2px; font-size: 0.75em; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;' title='{t['titulo']}'>📅 {titulo_corto}</div>"
                    
                    # Deadline
                    if fecha_f == str(dia_actual):
                        color = COLORES_TIPO.get(t.get('tipo'), "gray")
                        html_celda += f"<div style='border: 1px solid {color}; color: white; padding: 1px 3px; border-radius: 3px; margin-bottom: 2px; font-size: 0.75em; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;' title='{t['titulo']}'>⏰ {titulo_corto}</div>"
                
                html_celda += "</div>"
                
                # RENDER FINAL
                st.markdown(html_celda, unsafe_allow_html=True) # Cierre contenedor día


if __name__ == "__main__":
    main()
