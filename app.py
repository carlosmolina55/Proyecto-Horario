import streamlit as st
from github import Github, GithubException
import json
import pandas as pd
from datetime import datetime, date, timedelta, time
import calendar
import pytz
import os

# --- LIBRARIES FOR SCRAPING ---
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import time as time_lib

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(
    page_title="AutoGestor",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- CONSTANTES ---
FILE_PATH = "tareas.json"
REPO_NAME = "carlosmolina55/Proyecto-Horario"
TIMEZONE = pytz.timezone("Europe/Madrid")
HORARIO_FILE = "horario_clases.json" # Archivo local/remoto para clases scrapeadas

def get_madrid_time():
    return datetime.now(TIMEZONE)

def get_madrid_date():
    """Devuelve la fecha actual en Madrid"""
    return get_madrid_time().date()

# --- CONFIGURACIÓN DE USUARIO (CAMBIAR ESTO) ---
# Nombre del repositorio donde se guardará el archivo tareas.json
REPO_NAME = "carlosmolina55/Proyecto-Horario"
FILE_PATH = "tareas.json"



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

# Paleta de colores predeterminados para eventos
COLORES_PREDETERMINADOS = {
    "Azul": "#1E90FF",
    "Verde": "#2E8B57",
    "Rojo": "#FF4B4B",
    "Naranja": "#FF8C00",
    "Morado": "#8A2BE2",
    "Rosa": "#FF69B4",
    "Turquesa": "#00CED1",
    "Amarillo": "#FFD700",
    "Gris": "#708090",
    "Marrón": "#8B4513",
}

def render_selector_color(key_prefix, default_color="#1E90FF"):
    """Renderiza un selector de colores predeterminados con opción personalizada."""
    st.markdown("**🎨 Color**")
    
    # Obtener el color actual del session_state o usar default
    color_actual = st.session_state.get(f"{key_prefix}_color_selected", default_color)
    
    # Mostrar preview visual de todos los colores
    html_colors = "<div style='display:flex; flex-wrap:wrap; gap:6px; margin: 5px 0;'>"
    for nombre, hex_val in COLORES_PREDETERMINADOS.items():
        is_sel = (hex_val.upper() == color_actual.upper())
        border = "3px solid white" if is_sel else "2px solid #555"
        shadow = "0 0 8px " + hex_val if is_sel else "none"
        html_colors += f"<div style='width:28px; height:28px; background:{hex_val}; border-radius:6px; border:{border}; box-shadow:{shadow};' title='{nombre}'></div>"
    html_colors += "</div>"
    st.markdown(html_colors, unsafe_allow_html=True)
    
    # Selector funcional con radio horizontal
    use_custom = st.checkbox("🎨 Color personalizado", key=f"{key_prefix}_use_custom")
    if use_custom:
        color_actual = st.color_picker("Elige color", color_actual, key=f"{key_prefix}_custom_picker")
        st.session_state[f"{key_prefix}_color_selected"] = color_actual
    else:
        nombre_default_idx = 0
        for idx, (nombre, hex_val) in enumerate(COLORES_PREDETERMINADOS.items()):
            if hex_val.upper() == color_actual.upper():
                nombre_default_idx = idx
                break
        nombre_sel = st.radio("Color:", list(COLORES_PREDETERMINADOS.keys()), index=nombre_default_idx, key=f"{key_prefix}_radio_color", horizontal=True, label_visibility="collapsed")
        color_actual = COLORES_PREDETERMINADOS[nombre_sel]
        st.session_state[f"{key_prefix}_color_selected"] = color_actual
    
    return color_actual

def hex_to_rgba(hex_color, alpha=0.15):
    """Convierte un color hex a rgba con transparencia."""
    hex_color = hex_color.lstrip('#')
    if len(hex_color) == 3:
        hex_color = ''.join([c*2 for c in hex_color])
    try:
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)
        return f"rgba({r},{g},{b},{alpha})"
    except:
        return f"rgba(30,144,255,{alpha})"

# --- FUNCIONES DE SCRAPING (LOYOLA) ---

def init_driver():
    """Inicializa y devuelve una instancia de Chrome Driver"""
    options = webdriver.ChromeOptions()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_argument('--window-size=1920,1080')
    
    service = None
    # Detección de entorno (Linux/Cloud vs Local)
    possible_paths = [
        "/usr/bin/chromedriver",
        "/usr/lib/chromium-browser/chromedriver",
        "/usr/bin/chromium-browser"
    ]
    
    system_driver_path = None
    for p in possible_paths:
        if os.path.exists(p) and "driver" in p:
            system_driver_path = p
            break
    
    if system_driver_path:
        service = Service(system_driver_path)
        if os.path.exists("/usr/bin/chromium"):
            options.binary_location = "/usr/bin/chromium"
        elif os.path.exists("/usr/bin/chromium-browser"):
            options.binary_location = "/usr/bin/chromium-browser"
    else:
        try:
            service = Service(ChromeDriverManager().install())
        except: pass

    if not service:
        return None
        
    return webdriver.Chrome(service=service, options=options)

def actualizar_horario_clases(force=False, driver=None):
    """
    Scrapea la web de la universidad.
    Acepta driver opcional para reutilizar sesión.
    """
    # 1. Chequeo de Caché
    if not force and os.path.exists(HORARIO_FILE):
        try:
            last_mod = datetime.fromtimestamp(os.path.getmtime(HORARIO_FILE))
            if datetime.now() - last_mod < timedelta(hours=12):
                with open(HORARIO_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except: pass

    # 2. Configurar Selenium
    driver_propio = False
    if not driver:
        driver = init_driver()
        driver_propio = True
        
    if not driver:
        st.error("No se pudo iniciar el driver de Chrome.")
        return []
    
    data_clases = []
    
    try:
        url = "https://portales.uloyola.es/LoyolaHorario/horario.xhtml?curso=2025%2F26&tipo=M&titu=2175&campus=2&ncurso=1&grupo=A"
        driver.get(url)
        
        # Esperar carga inicial
        wait = WebDriverWait(driver, 15)
        wait.until(EC.presence_of_element_located((By.CLASS_NAME, "fc-view-harness")))
        
        # Iterar 12 semanas (3 meses aprox)
        weeks_to_scrape = 12
        current_year = get_madrid_date().year
        
        for _ in range(weeks_to_scrape):
            try:
                try:
                    WebDriverWait(driver, 5).until(
                        EC.presence_of_element_located((By.CLASS_NAME, "fc-event"))
                    )
                except: pass
                
                time_lib.sleep(1.5)

                headers = driver.find_elements(By.CLASS_NAME, "fc-col-header-cell")
                column_map = []
                
                for h in headers:
                    d_date = h.get_attribute("data-date")
                    if d_date:
                        rect = h.rect
                        column_map.append({
                            "date": d_date,
                            "x_start": rect['x'],
                            "x_end": rect['x'] + rect['width']
                        })
                
                events = driver.find_elements(By.CLASS_NAME, "fc-event")
                
                for ev in events:
                    try:
                        ev_rect = ev.rect
                        ev_center_x = ev_rect['x'] + (ev_rect['width'] / 2)
                        
                        fecha_clase = None
                        for col in column_map:
                            if col['x_start'] <= ev_center_x <= col['x_end']:
                                fecha_clase = col['date']
                                break
                        
                        if not fecha_clase: continue
                        
                        full_text = ev.text 
                        try:
                            hora_text = ev.find_element(By.CLASS_NAME, "fc-event-time").text
                            content_text = ev.find_element(By.CLASS_NAME, "fc-event-title").text
                        except:
                            lines = full_text.split('\n')
                            hora_text = lines[0] if lines else ""
                            content_text = lines[1] if len(lines) > 1 else ""

                        parts = content_text.split("/")
                        asig = parts[0].strip()
                        aula = parts[1].replace("Aula:", "").strip() if len(parts) > 1 else "Desconocido"
                        
                        try:
                            h_parts = hora_text.split("-")
                            new_times = []
                            for hp in h_parts:
                                t_obj = datetime.strptime(hp.strip(), "%H:%M")
                                t_new = t_obj + timedelta(hours=1)
                                new_times.append(t_new.strftime("%H:%M"))
                            
                            hora_text = f"{new_times[0]} - {new_times[1]}"
                        except: pass

                        data_clases.append({
                            "asignatura": asig,
                            "titulo": asig,
                            "aula": aula,
                            "fecha": fecha_clase,
                            "hora": hora_text,
                            "dia_completo": False
                        })
                        
                    except Exception as e_ev: pass
                
                try:
                    btn_next = driver.find_element(By.CLASS_NAME, "fc-next-button")
                    btn_next.click()
                    time_lib.sleep(1.0) 
                except: break 
                   
            except Exception as e: break

        if driver_propio:
            driver.quit()
        
        # Guardar en JSON local
        with open(HORARIO_FILE, 'w', encoding='utf-8') as f:
            json.dump(data_clases, f, indent=4, ensure_ascii=False)
            
        return data_clases

    except Exception as e:
        st.error(f"Error actualizando horario: {e}")
        if driver_propio: driver.quit()
        return []

def actualizar_horario_sevilla(driver=None):
    """Scrapea SOLO partidos en CASA del Sevilla FC (Nervión)."""
    driver_propio = False
    if not driver:
        driver = init_driver()
        driver_propio = True
        
    if not driver: return []
    
    data_futbol = []
    try:
        url = "https://www.laliga.com/clubes/sevilla-fc/proximos-partidos"
        driver.get(url)
        
        # Cookies: Intentar varios textos
        try:
            btns = driver.find_elements(By.TAG_NAME, "button")
            for b in btns:
                txt = b.text.lower()
                if "aceptar" in txt or "accept" in txt or "consentir" in txt:
                    b.click()
                    break
            time_lib.sleep(1)
        except: pass
        
        import re
        
        time_lib.sleep(2)  # Esperar carga de la tabla
        filas = driver.find_elements(By.TAG_NAME, "tr")
        
        for fila in filas:
            if "more-info" in (fila.get_attribute("class") or ""): continue
            
            try:
                texto_fila = fila.text
                if not texto_fila: continue
                
                # 1. Buscar Fecha (DD.MM.YYYY)
                match_fecha = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", texto_fila)
                if not match_fecha: continue
                
                dia = int(match_fecha.group(1))
                mes = int(match_fecha.group(2))
                anio = int(match_fecha.group(3))
                fecha_obj = date(anio, mes, dia)
                fecha_iso = fecha_obj.strftime("%Y-%m-%d")
                
                # 2. Buscar Hora (HH:MM o -- : --)
                match_hora = re.search(r"(\d{2}:\d{2})", texto_fila)
                if match_hora:
                    hora_txt = match_hora.group(1)
                    es_dia_completo = False
                else:
                    hora_txt = None
                    es_dia_completo = True
                
                # 3. Detectar si es partido en CASA
                # En la tabla: Local VS Visitante
                # Si el primer equipo (antes de VS) es Sevilla FC → juega en casa
                lineas = [l.strip() for l in texto_fila.split('\n') if l.strip()]
                
                idx_vs = -1
                for i, l in enumerate(lineas):
                    if l.upper() == "VS":
                        idx_vs = i
                        break
                
                if idx_vs <= 0: continue
                
                local_name = lineas[idx_vs - 1].lower()
                
                # Solo guardar si Sevilla es LOCAL (juega en casa / Nervión)
                es_casa = "sevilla" in local_name
                if not es_casa:
                    continue

                data_futbol.append({
                    "titulo": "⚽ Partido en Nervión",
                    "asignatura": "Fútbol",
                    "aula": "Nervión",
                    "fecha": fecha_iso,
                    "hora": hora_txt,
                    "dia_completo": es_dia_completo,
                    "es_futbol": True
                })
                
            except Exception:
                pass
                
        if driver_propio: driver.quit()
        
        # Guardar
        with open("horario_futbol.json", 'w', encoding='utf-8') as f:
            json.dump(data_futbol, f, indent=4, ensure_ascii=False)
            
        return data_futbol

    except Exception as e:
        st.error(f"Error cargando fútbol: {e}")
        if driver_propio: driver.quit()
        return []

# --- GESTIÓN DE PERSISTENCIA (GITHUB) ----

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

def gestionar_horario(accion, nuevo_item=None, id_eliminar=None, item_actualizado=None):
    """
    Gestiona el archivo horario.json en GitHub.
    """
    token = st.secrets["GITHUB_TOKEN"]
    g = Github(token)
    repo = g.get_repo(REPO_NAME)
    file_path = "horario.json"
    
    try:
        contents = repo.get_contents(file_path)
        data = json.loads(contents.decoded_content.decode())
    except:
        data = [] 

    if accion == 'leer':
        return data

    elif accion == 'crear':
        data.append(nuevo_item)
        mensaje = "Nuevo horario/evento añadido"

    elif accion == 'borrar':
        data = [t for t in data if t['id'] != id_eliminar]
        mensaje = "Elemento eliminado"

    elif accion == 'actualizar':
        for index, item in enumerate(data):
            if item['id'] == item_actualizado['id']:
                data[index] = item_actualizado
                break
        mensaje = "Horario actualizado"
    
    # GUARDAR
    try:
        updated_content = json.dumps(data, indent=4)
        if 'contents' in locals():
             repo.update_file(contents.path, mensaje, updated_content, contents.sha)
        else:
             repo.create_file(file_path, "Init horario", updated_content)
        return True
    except Exception as e:
        st.error(f"Error guardando horario: {e}")
        return False


# --- IMPLEMENTACIÓN DE VISTAS ---

def render_vista_nuevo_horario():
    st.subheader("➕ Añadir Nuevo Evento")
    
    with st.container(border=True):
        c_conf, c_form = st.columns([1, 3])
        
        with c_conf:
            st.info("Tipo de Entrada")
            tipo_entrada = st.radio("¿Qué vas a añadir?", ["📅 Evento Único", "📅 Evento Multi-día", "🔄 Rutina Semanal"], key="type_schedule")
            st.caption("Evento: Ocurre un día específico (ej. Cita médico).\nMulti-día: Abarca varios días (ej. Viaje).\nRutina: Se repite todas las semanas (ej. Gym).")
            
            st.write("")
            color_evento = render_selector_color("evento_new")
            
        with c_form:
            titulo = st.text_input("Título del evento", placeholder="Ej: Cita médico, Gimnasio, Reunión, Viaje Italia...")
            
            c1, c2 = st.columns(2)
            ubicacion = c1.text_input("📍 Ubicación", placeholder="Ej: Hospital, Gym, Online...")
            descripcion = c2.text_area("📝 Descripción (opcional)", placeholder="Detalles adicionales...", height=68)
            
            # Lógica Rutina vs Evento vs Multi-día
            dias_seleccionados = []
            fecha_evento = None
            fecha_fin_evento = None
            
            if "Rutina" in tipo_entrada:
                st.write("Selecciona los días:")
                cols_dias = st.columns(7)
                dias_abv = ["L", "M", "X", "J", "V", "S", "D"]
                for i, col in enumerate(cols_dias):
                    if col.checkbox(dias_abv[i], key=f"d_{i}"):
                        dias_seleccionados.append(i)
            elif "Multi-día" in tipo_entrada:
                cf1, cf2 = st.columns(2)
                fecha_evento = cf1.date_input("📅 Fecha de inicio", get_madrid_date(), key="fecha_inicio_multi")
                fecha_fin_evento = cf2.date_input("📅 Fecha de fin", get_madrid_date() + timedelta(days=2), key="fecha_fin_multi")
                if fecha_fin_evento < fecha_evento:
                    st.error("⚠️ La fecha de fin no puede ser anterior a la de inicio.")
            else:
                fecha_evento = st.date_input("Fecha del Evento", get_madrid_date())
                
            # Horas
            st.write("🕒 Horario:")
            ch1, ch2, ch3 = st.columns([1, 1, 1])
            h_inicio = ch1.time_input("Hora Inicio", datetime.strptime("10:00", "%H:%M").time())
            h_fin = ch2.time_input("Hora Fin", datetime.strptime("11:00", "%H:%M").time())
            dia_completo = ch3.checkbox("📅 Todo el día", value=("Multi-día" in tipo_entrada), key="chk_all_day_event")
            
            st.write("")
            if st.button("💾 Guardar Evento", type="primary", use_container_width=True):
                if not titulo:
                    st.error("El título es obligatorio")
                    return
                
                if "Rutina" in tipo_entrada and not dias_seleccionados:
                    st.error("Selecciona al menos un día para la rutina.")
                    return
                
                if "Multi-día" in tipo_entrada and fecha_fin_evento and fecha_fin_evento < fecha_evento:
                    st.error("⚠️ La fecha de fin no puede ser anterior a la de inicio.")
                    return

                es_multidia = "Multi-día" in tipo_entrada
                nuevo_item = {
                    "id": int(get_madrid_time().timestamp()),
                    "titulo": titulo,
                    "ubicacion": ubicacion,
                    "descripcion": descripcion,
                    "color": color_evento,
                    "tipo": "Rutina" if "Rutina" in tipo_entrada else "Evento",
                    "es_rutina": "Rutina" in tipo_entrada,
                    "es_multidia": es_multidia,
                    "dias_semana": dias_seleccionados,
                    "fecha": str(fecha_evento) if fecha_evento else None,
                    "fecha_fin_evento": str(fecha_fin_evento) if es_multidia and fecha_fin_evento else None,
                    "hora_inicio": str(h_inicio.strftime("%H:%M")) if not dia_completo else None,
                    "hora_fin": str(h_fin.strftime("%H:%M")) if not dia_completo else None,
                    "dia_completo": dia_completo
                }
                
                gestionar_horario('crear', nuevo_item=nuevo_item)
                st.session_state["mensaje_global"] = {"tipo": "exito", "texto": "💾 Evento guardado correctamente"}
                st.rerun()

def render_vista_nueva_tarea():
    st.subheader("➕ Añadir Nueva Tarea")
    
    with st.container(border=True):
        st.markdown("##### Datos de la Tarea")
        
        tit = st.text_input("Título de la tarea", key="tit_new")
        
        c1, c2 = st.columns(2)
        
        # Siempre deadline
        f_fin = c1.date_input("📅 Fecha Límite", get_madrid_date(), key="date_deadline_new")
        
        # HORA
        chk_dia_completo = c2.checkbox("📅 Todo el día", value=True, key="chk_all_day_new")
        
        hora_seleccionada = None
        if not chk_dia_completo:
            hora_defecto = datetime.now().time().replace(minute=0, second=0)
            hora_seleccionada = c2.time_input("🕒 Hora límite", hora_defecto, step=900, key="time_new")
        
        # RESTO DE CAMPOS
        prio = c1.selectbox("Prioridad", ["Normal", "Importante", "Urgente"], key="prio_new")
        tipo = c2.selectbox("Tipo / Asignatura", list(COLORES_TIPO.keys())[:-1], key="type_new")  # Excluir 'Clase'
        
        st.write("")
        
        # BOTON GUARDAR
        if st.button("💾 Guardar Tarea", type="primary", use_container_width=True):
            if not tit:
                st.error("⚠️ El título es obligatorio.")
            else:
                nt = {
                    "id": int(get_madrid_time().timestamp()), 
                    "titulo": tit, 
                    "prioridad": prio, 
                    "tipo": tipo, 
                    "estado": "Pendiente", 
                    "fecha": str(get_madrid_date()), 
                    "fecha_fin": str(f_fin),
                    "dia_completo": chk_dia_completo,
                    "hora": str(hora_seleccionada.strftime("%H:%M")) if hora_seleccionada else None
                }
                gestionar_tareas('crear', nueva_tarea=nt)
                st.session_state["mensaje_global"] = {"tipo": "exito", "texto": "💾 Tarea guardada correctamente"}
                st.rerun()

def render_vista_gestionar_todas(tareas):
    st.subheader("📋 Gestión Global")
    
    tab_tareas, tab_horario = st.tabs(["📝 Tareas", "📅 Horarios y Eventos"])
    
    with tab_tareas:
        # --- TAB TAREAS (lo que ya existia) ---
        tareas_pendientes = [t for t in tareas if t['estado'] != 'Completada']
        tareas_completadas = [t for t in tareas if t['estado'] == 'Completada']
        
        # Ordenar pendientes: Prioridad (Urgente > Importante > Normal) y Fecha
        def sort_key(t):
            prio_map = {"Urgente": 0, "Importante": 1, "Normal": 2}
            fecha_str = t.get('fecha_fin') if t.get('fecha_fin') else t.get('fecha')
            return (prio_map.get(t['prioridad'], 3), fecha_str)
        
        tareas_pendientes.sort(key=sort_key)
        
        st.markdown(f"**Pendientes: {len(tareas_pendientes)}**")
        for t in tareas_pendientes:
            render_tarjeta_gestion(t)
            
        st.divider()
        with st.expander(f"Completadas ({len(tareas_completadas)})"):
            for t in tareas_completadas:
                render_tarjeta_gestion(t)

    with tab_horario:
        # --- TAB HORARIOS / EVENTOS ---
        st.caption("Aquí puedes borrar rutinas o eventos creados manualmente.")
        
        horario = gestionar_horario('leer')
        
        if not horario:
            st.info("No hay horarios ni eventos personalizados creados.")
        else:
            # Separar y Ordenar
            eventos_unicos = [h for h in horario if not h.get('es_rutina')]
            rutinas = [h for h in horario if h.get('es_rutina')]
            
            # Ordenar eventos por fecha (Ascendente: Mas antiguos/hoy primero -> Futuro)
            # El usuario dijo "reciente a mas lejano", entendemos cronologico.
            eventos_unicos.sort(key=lambda x: x.get('fecha', '9999-99-99'))
            
            lista_ordenada = eventos_unicos + rutinas
            
            for h in lista_ordenada:
                with st.container(border=True):
                    c1, c2 = st.columns([5, 2])
                    
                    if h.get('es_multidia'):
                        titulo_h = f"�️ {h['titulo']}"
                    elif h.get('es_rutina'):
                        titulo_h = f"🔄 {h['titulo']}"
                    else:
                        titulo_h = f"📅 {h['titulo']}"
                    
                    info_extra = ""
                    if h.get('es_rutina'):
                        dias_map = ["L", "M", "X", "J", "V", "S", "D"]
                        dias_str = ", ".join([dias_map[i] for i in h.get('dias_semana', [])])
                        info_extra = f" | Días: {dias_str}"
                    elif h.get('es_multidia') and h.get('fecha_fin_evento'):
                        info_extra = f" | 📅 {h.get('fecha')} → {h.get('fecha_fin_evento')}"
                    else:
                        info_extra = f" | Fecha: {h.get('fecha')}"
                    
                    hora_display = ""
                    if h.get('hora_inicio') and h.get('hora_fin'):
                        hora_display = f" ({h['hora_inicio']} - {h['hora_fin']})"
                    elif h.get('dia_completo'):
                        hora_display = " (Todo el día)"
                    
                    c1.markdown(f"**{titulo_h}**{hora_display}")
                    c1.caption(f"{h.get('ubicacion', '')}{info_extra}")
                    
                    with c2:
                         ca_edit, ca_del = st.columns(2)
                         
                         # Boton Editar (Popover)
                         with ca_edit.popover("✏️", help="Editar"):
                            with st.form(f"edit_h_form_{h['id']}"):
                                st.write("📝 **Editar Evento**")
                                e_titulo = st.text_input("Título", h['titulo'])
                                e_ubicacion = st.text_input("Ubicación", h.get('ubicacion',''))
                                idx_tipo = ["Clase", "Estudio", "Rutina", "Evento", "Otro"].index(h.get('tipo', 'Evento')) if h.get('tipo') in ["Clase", "Estudio", "Rutina", "Evento", "Otro"] else 3
                                e_tipo = st.selectbox("Tipo", ["Clase", "Estudio", "Rutina", "Evento", "Otro"], index=idx_tipo)
                                
                                e_es_rutina = st.toggle("Rutina Semanal", h.get('es_rutina'))
                                
                                c_f1, c_f2 = st.columns(2)
                                e_dias_sel = []
                                e_fecha_str = None
                                
                                if e_es_rutina:
                                    dias_map = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
                                    def_dias = [dias_map[i] for i in h.get('dias_semana', [])]
                                    with c_f1: dias_txt = st.multiselect("Días", dias_map, default=def_dias)
                                    e_dias_sel = [dias_map.index(d) for d in dias_txt]
                                else:
                                    try: def_dt = datetime.strptime(h.get('fecha', get_madrid_date().strftime("%Y-%m-%d")), "%Y-%m-%d").date()
                                    except: def_dt = get_madrid_date()
                                    with c_f1: e_fecha = st.date_input("Fecha", def_dt)
                                    e_fecha_str = str(e_fecha)
                                
                                # Horas
                                try: t_i = datetime.strptime(h.get('hora_inicio', '09:00'), "%H:%M").time()
                                except: t_i = time(9,0)
                                try: t_f = datetime.strptime(h.get('hora_fin', '10:00'), "%H:%M").time()
                                except: t_f = time(10,0)
                                
                                with c_f2: e_h_ini = st.time_input("Inicio", t_i)
                                with c_f2: e_h_fin = st.time_input("Fin", t_f)
                                
                                if st.form_submit_button("Guardar Cambios", type="primary"):
                                    h['titulo'] = e_titulo
                                    h['ubicacion'] = e_ubicacion
                                    h['tipo'] = e_tipo
                                    h['es_rutina'] = e_es_rutina
                                    h['hora_inicio'] = e_h_ini.strftime("%H:%M")
                                    h['hora_fin'] = e_h_fin.strftime("%H:%M")
                                    
                                    if e_es_rutina:
                                        h['dias_semana'] = e_dias_sel
                                        h['fecha'] = None
                                    else:
                                        h['dias_semana'] = []
                                        h['fecha'] = e_fecha_str
                                    
                                    gestionar_horario('actualizar', item_actualizado=h)
                                    st.session_state["mensaje_global"] = {"tipo": "exito", "texto": "✏️ Evento actualizado"}
                                    st.rerun()

                         # Boton Borrar
                         if ca_del.button("🗑️", key=f"del_h_{h['id']}", help="Borrar"):
                            gestionar_horario('borrar', id_eliminar=h['id'])
                            st.session_state["mensaje_global"] = {"tipo": "exito", "texto": "🗑️ Evento/Horario eliminado"}
                            st.rerun()

def render_tarjeta_gestion(t):
    """Auxiliar para pintar la tarjeta de una tarea en la lista de gestión"""
    # Icono y Color
    estado_icon = "✅" if t['estado'] == 'Completada' else "⬜"
    color_borde = COLORES_PRIORIDAD.get(t.get('prioridad', 'Normal'), "gray")
    bg_opacity = "0.5" if t['estado'] == 'Completada' else "1"
    
    with st.container(border=True):
        c_main, c_actions = st.columns([5, 2]) # Ampliar columna acciones
        
        with c_main:
            # Título grande (SIN HORA)
            st.markdown(f"<h4 style='margin:0; opacity:{bg_opacity}'>{estado_icon} {t['titulo']}</h4>", unsafe_allow_html=True)
            
            # Determinamos qué fecha mostrar
            # Si tiene fecha_fin, es un Deadline. Si no, es fecha fija.
            
            # Construir string fecha/hora
            str_fecha = ""
            str_hora = ""
            
            if not t.get('dia_completo', True) and t.get('hora'):
                str_hora = f" @ {t['hora']}"
            
            if t.get('fecha_fin'):
                 f_display = f"⏰ Deadline: {t['fecha_fin']}{str_hora}"
            else:
                 f_display = f"📅 {t['fecha']}{str_hora}"
            
            # Prioridad con color
            color_prio = "red" if t['prioridad'] == "Urgente" else "orange" if t['prioridad'] == "Importante" else "green"
            
            st.markdown(f"<span style='color:{color_prio}; font-weight:bold'>{t['prioridad']}</span> | {t['tipo']} | **{f_display}**", unsafe_allow_html=True)
            
        with c_actions:
            # Botones de acción en columnas pequeñas
            ca1, ca2, ca3 = st.columns(3)
            
            # 1. Completar / Desmarcar
            if t['estado'] != 'Completada':
                if ca1.button("✅", key=f"ok_main_{t['id']}", help="Marcar como completada"):
                    t['estado'] = 'Completada'
                    gestionar_tareas('actualizar', tarea_actualizada=t)
                    st.rerun()
            else:
                if ca1.button("↩️", key=f"undo_main_{t['id']}", help="Deshacer (Marcar pendiente)"):
                    t['estado'] = 'Pendiente'
                    gestionar_tareas('actualizar', tarea_actualizada=t)
                    st.rerun()

            # 2. Editar
            with ca2.popover("✏️"):
                with st.form(f"edit_main_{t['id']}"):
                    e_titulo = st.text_input("Título", t['titulo'])
                    
                    # FECHAS
                    es_deadline = t.get('fecha_fin') is not None
                    if es_deadline:
                        try:
                            fecha_base = datetime.strptime(t['fecha_fin'], "%Y-%m-%d").date()
                        except: fecha_base = get_madrid_date()
                        e_fecha = st.date_input("Deadline", fecha_base)
                    else:
                        try:
                            fecha_base = datetime.strptime(t['fecha'], "%Y-%m-%d").date()
                        except: fecha_base = get_madrid_date()
                        e_fecha = st.date_input("Fecha", fecha_base)
                    
                    # HORA
                    e_dia_completo = st.checkbox("📅 Todo el día", value=t.get('dia_completo', True))
                    e_hora = None
                    if not e_dia_completo:
                        try:
                            hora_default = datetime.strptime(t.get('hora', "09:00"), "%H:%M").time()
                        except: hora_default = datetime.now().time()
                        e_hora_input = st.time_input("Hora", hora_default)
                        e_hora = e_hora_input.strftime("%H:%M")

                    e_estado = st.selectbox("Estado", ["Pendiente", "Completada"], index=0 if t['estado']=="Pendiente" else 1)
                    e_prioridad = st.selectbox("Prioridad", ["Normal", "Importante", "Urgente"], index=["Normal", "Importante", "Urgente"].index(t.get('prioridad', 'Normal')))
                    
                    if st.form_submit_button("Guardar"):
                        t['titulo'] = e_titulo
                        t['estado'] = e_estado
                        t['prioridad'] = e_prioridad
                        t['dia_completo'] = e_dia_completo
                        t['hora'] = e_hora
                        
                        if es_deadline: t['fecha_fin'] = str(e_fecha)
                        else: t['fecha'] = str(e_fecha)
                        gestionar_tareas('actualizar', tarea_actualizada=t)
                        st.session_state["mensaje_global"] = {"tipo": "exito", "texto": "✏️ Tarea actualizada"}
                        st.rerun()
                        
                            
            # 3. Borrar
            if ca3.button("🗑️", key=f"del_main_{t['id']}", help="Borrar tarea"):
                gestionar_tareas('borrar', id_tarea_eliminar=t['id'])
                st.session_state["mensaje_global"] = {"tipo": "exito", "texto": "🗑️ Tarea eliminada"}
                st.rerun()

# --- DIÁLOGO DE DETALLES ---

@st.dialog("Detalles")
def mostrar_detalle_item(item):
    # Cabecera con Icono y Título
    tipo = item.get('tipo', 'Evento')
    titulo = item.get('titulo', 'Sin título')
    
    col_icon, col_tit = st.columns([1, 5])
    with col_icon:
        if item.get('es_universidad'): st.subheader("📖")
        elif item.get('es_rutina'): st.subheader("🔄")
        elif tipo == 'tarea': st.subheader("📝")
        else: st.subheader("📅")
    
    with col_tit:
        st.subheader(titulo)
        st.caption(f"Tipo: {tipo}")
        
    st.divider()
    
    # Información General
    c1, c2 = st.columns(2)
    
    # Lógica para determinar la hora
    hora_str = item.get('hora')
    if not hora_str and item.get('hora_inicio') and item.get('hora_fin'):
         hora_str = f"{item['hora_inicio']} - {item['hora_fin']}"
    if not hora_str:
         hora_str = 'Todo el día'
         
    c1.markdown(f"**🕒 Hora:** {hora_str}")
    if item.get('ubicacion'): c1.markdown(f"**📍 Ubicación:** {item['ubicacion']}")
    # Aula para clases
    if item.get('aula'): c1.markdown(f"**📍 Aula:** {item['aula']}")
    
    if item.get('fecha'): c2.markdown(f"**📅 Fecha:** {item['fecha']}")
    
    if item.get('dias_semana'):
        dias_map_str = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
        s_dias = [dias_map_str[i] for i in item['dias_semana']]
        c2.markdown(f"**🔄 Días:** {', '.join(s_dias)}")
    
    if item.get('descripcion'):
        st.markdown(f"**📝 Descripción:** {item['descripcion']}")

    # Acciones específicas
    st.divider()
    
    if tipo == 'tarea':
        st.write(f"**Prioridad:** {item.get('prioridad', 'Normal')}")
        if item.get('msg'): st.info(item['msg'])
        
        if item.get('estado') != 'Completada':
            if st.button("✅ Marcar como Completada", use_container_width=True):
                item['estado'] = 'Completada'
                gestionar_tareas('actualizar', tarea_actualizada=item)
                st.session_state["mensaje_global"] = {"tipo": "exito", "texto": "Tarea completada"}
                st.rerun()
        else:
            st.success("✅ Tarea ya completada")
            
    elif item.get('es_rutina') or (not item.get('es_universidad') and item.get('id')):
        # Es un evento manual (Rutina o Evento unico) -> Se puede borrar
        if st.button("🗑️ Eliminar Evento", type="primary", use_container_width=True):
            if gestionar_horario('borrar', id_eliminar=item['id']):
                st.session_state["mensaje_global"] = {"tipo": "exito", "texto": "Evento eliminado"}
                st.rerun()
            else:
                 st.error("Error al eliminar")
            
    elif item.get('es_universidad'):
        st.info("ℹ️ Este evento pertenece al horario universitario oficial.")

# --- UI Y LÓGICA ---

def main():
    st.title("🎓 AutoGestor")

    # --- NOTIFICACIONES GLOBLALES ---
    if "mensaje_global" in st.session_state and st.session_state["mensaje_global"]:
        tipo = st.session_state["mensaje_global"]["tipo"]
        texto = st.session_state["mensaje_global"]["texto"]
        if tipo == "exito":
            st.success(texto)
        elif tipo == "error":
            st.error(texto)
        st.session_state["mensaje_global"] = None
        
    # --- AUTO-UPDATE HORARIO CLASES ---
    # Comentado para no bloquear al inicio, se usa manual
    # with st.spinner("Sincronizando horario universitario..."):
    #     horario_clases_scraped = actualizar_horario_clases()
    
    # Cargar Horario Clases (Cache)
    try:
        with open(HORARIO_FILE, 'r', encoding='utf-8') as f:
            horario_clases_scraped = json.load(f)
    except:
        horario_clases_scraped = []
        
    # Cargar Horario Futbol (Cache)
    try:
        with open("horario_futbol.json", 'r', encoding='utf-8') as f:
            horario_futbol_scraped = json.load(f)
    except:
        horario_futbol_scraped = []
        
    # --- GESTOR DE DATOS (PERSISTENCIA) ---
    tareas = gestionar_tareas('leer')
    horario_dinamico = gestionar_horario('leer')
    
    # --- LIMPIEZA AUTOMÁTICA ---
    hoy_real = get_madrid_date()
    tareas_filtradas = []
    hubo_cambios_limpieza = False
    
    for t in tareas:
        # Si es completada y vieja, fuera
        es_vieja = False
        try:
            if t.get('fecha'):
                f_t = datetime.strptime(t['fecha'], "%Y-%m-%d").date()
                if f_t < hoy_real: es_vieja = True
            if t.get('fecha_fin'): # Si tiene deadline y ya pasó hace tiempo también
                f_f = datetime.strptime(t['fecha_fin'], "%Y-%m-%d").date()
                if f_f < hoy_real: es_vieja = True
        except: pass
            
        if t['estado'] == 'Completada' and es_vieja:
            # Solo borrar si ya pasó el día
             hubo_cambios_limpieza = True
        else:
            tareas_filtradas.append(t)
            
    if hubo_cambios_limpieza:
        if gestionar_tareas('guardar_todo', lista_completa=tareas_filtradas):
            st.toast("🧹 Se han eliminado tareas antiguas automáticamente.")
            tareas = tareas_filtradas

    # --- SIDEBAR GLOBAL ---
    with st.sidebar:
        st.header("👁️ Navegación")
        # Menú ampliado
        opciones_navegacion = ["Diaria", "Semanal", "Mensual", "---", "➕ Nueva Tarea", "➕ Nuevo Evento/Horario", "📋 Gestionar Todas"]
        vista_actual = st.radio("Ir a:", opciones_navegacion, index=0, label_visibility="collapsed")
        
        st.divider()
        st.header("📅 Control de Fecha")
        
        # Botón HOY para volver al día presente
        if st.button("Ir a Hoy", use_container_width=True, type="primary"):
            st.session_state["fecha_base_manual"] = get_madrid_date()
            st.session_state["date_input_sidebar"] = get_madrid_date()
            st.rerun()
        
        # Usar la fecha guardada en session_state si existe, si no usar la de hoy
        fecha_default = st.session_state.get("fecha_base_manual", get_madrid_date())
        fecha_seleccionada = st.date_input("Fecha Base", fecha_default, key="date_input_sidebar")
        
        # Guardar cambio manual del date_input
        if fecha_seleccionada != fecha_default:
            st.session_state["fecha_base_manual"] = fecha_seleccionada
        
        st.info(f"Mirando: **{fecha_seleccionada.strftime('%d %b %Y')}**")
        
        if st.button("🔄 Actualizar Horario"):
            with st.spinner("Actualizando Loyola y Sevilla FC..."):
                driver = init_driver()
                actualizar_horario_clases(force=True, driver=driver)
                actualizar_horario_sevilla(driver=driver)
                if driver: driver.quit()
            st.rerun()

    # --- ENRUTADOR DE VISTAS ---
    if vista_actual == "Diaria":
        render_vista_diaria(tareas, fecha_seleccionada, horario_dinamico, horario_clases_scraped, horario_futbol_scraped)
    elif vista_actual == "Semanal":
        render_vista_semanal(tareas, fecha_seleccionada, horario_dinamico, horario_clases_scraped, horario_futbol_scraped)
    elif vista_actual == "Mensual":
        render_vista_mensual(tareas, fecha_seleccionada, horario_dinamico, horario_clases_scraped, horario_futbol_scraped)
    elif vista_actual == "➕ Nueva Tarea":
        render_vista_nueva_tarea()
    elif vista_actual == "➕ Nuevo Evento/Horario":
        render_vista_nuevo_horario()
    elif vista_actual == "📋 Gestionar Todas":
        render_vista_gestionar_todas(tareas)

# --- IMPLEMENTACIÓN DE VISTAS ---

def render_vista_diaria(tareas, fecha_seleccionada, horario_dinamico, horario_clases_scraped, horario_futbol_scraped):
    # --- NAVEGACIÓN CON FLECHAS ---
    nav_c1, nav_c2, nav_c3 = st.columns([1, 3, 1])
    with nav_c1:
        if st.button("◀ Anterior", key="prev_day", use_container_width=True):
            new_d = fecha_seleccionada - timedelta(days=1)
            st.session_state["fecha_base_manual"] = new_d
            st.session_state["date_input_sidebar"] = new_d
            st.rerun()
    with nav_c2:
        dias_es = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
        dia_nombre = dias_es[fecha_seleccionada.weekday()]
        st.markdown(f"<h3 style='text-align:center; margin:0;'>{dia_nombre} {fecha_seleccionada.day}/{fecha_seleccionada.month}/{fecha_seleccionada.year}</h3>", unsafe_allow_html=True)
    with nav_c3:
        if st.button("Siguiente ▶", key="next_day", use_container_width=True):
            new_d = fecha_seleccionada + timedelta(days=1)
            st.session_state["fecha_base_manual"] = new_d
            st.session_state["date_input_sidebar"] = new_d
            st.rerun()
    
    st.divider()
    
    # --- AVISO DE TAREAS ATRASADAS ---
    hoy_real = get_madrid_date()
    tareas_atrasadas = []
    
    for t in tareas:
        if t.get('estado') == 'Completada': continue
        
        fecha_ref = None
        if t.get('fecha_fin'):
            try: fecha_ref = datetime.strptime(t['fecha_fin'], "%Y-%m-%d").date()
            except: pass
        elif t.get('fecha'):
            try: fecha_ref = datetime.strptime(t['fecha'], "%Y-%m-%d").date()
            except: pass
            
        if fecha_ref and fecha_ref < hoy_real:
             tareas_atrasadas.append(t)
            
    if tareas_atrasadas:
        st.error(f"🚨 Tienes {len(tareas_atrasadas)} tareas atrasadas pendientes")
        with st.expander("Ver tareas atrasadas"):
            for atrasada in tareas_atrasadas:
                f_str = atrasada.get('fecha_fin') or atrasada.get('fecha')
                st.markdown(f"🔴 **{atrasada['titulo']}** (📅 {f_str})")

    col_horario, col_tareas = st.columns([1, 2])
    
    with col_horario:
        st.subheader("🏫 Horario")
        dia_semana = fecha_seleccionada.weekday()
        
        # Recolectar items del dia
        clases_hoy = []
        
        # 1. Clases Scrapeadas (Fecha exacta)
        fecha_sel_str = str(fecha_seleccionada)
        for c in horario_clases_scraped:
            if c['fecha'] == fecha_sel_str:
                clases_hoy.append({
                    "hora": c['hora'],
                    "asignatura": c['asignatura'],
                    "aula": c['aula'],
                    "es_universidad": True
                })
        
        # 1.5 Futbol Scrapeado
        for f in horario_futbol_scraped:
             if f['fecha'] == fecha_sel_str:
                 h_txt = f['hora'] if f['hora'] else "Todo el día"
                 clases_hoy.append({
                     "hora": h_txt,
                     "asignatura": f["titulo"],
                     "aula": f["aula"],
                     "es_futbol": True
                 })

        # 2. Horario Dinámico (JSON)
        for item in horario_dinamico:
            es_hoy = False
            if item.get('es_rutina'):
                if dia_semana in item.get('dias_semana', []):
                    es_hoy = True
            elif item.get('es_multidia') and item.get('fecha') and item.get('fecha_fin_evento'):
                # Evento multi-día: comprobar si fecha_seleccionada está en el rango
                try:
                    f_inicio_m = datetime.strptime(item['fecha'], "%Y-%m-%d").date()
                    f_fin_m = datetime.strptime(item['fecha_fin_evento'], "%Y-%m-%d").date()
                    if f_inicio_m <= fecha_seleccionada <= f_fin_m:
                        es_hoy = True
                except: pass
            else:
                if item.get('fecha') == fecha_sel_str:
                    es_hoy = True
            
            if es_hoy:
                hora_display = "Todo el día"
                if not item.get('dia_completo') and item.get('hora_inicio') and item.get('hora_fin'):
                    hora_display = f"{item['hora_inicio']} - {item['hora_fin']}"
                
                # Etiqueta multi-día
                multidia_label = ""
                if item.get('es_multidia') and item.get('fecha') and item.get('fecha_fin_evento'):
                    multidia_label = f" (🗓️ {item['fecha']} → {item['fecha_fin_evento']})"
                
                clases_hoy.append({
                    "hora": hora_display,
                    "asignatura": item['titulo'] + multidia_label,
                    "aula": item.get('ubicacion', ''),
                    "descripcion": item.get('descripcion', ''),
                    "color": item.get('color'),
                    "es_dinamico": True
                })
        
        # Ordenar por hora inicio
        def sort_hora(x):
            try:
                return x['hora'].split('-')[0].strip()
            except: return "23:59"
            
        clases_hoy.sort(key=sort_hora)

        if clases_hoy:
            for clase in clases_hoy:
                # Usar color personalizado si existe
                color_borde = clase.get('color', '#2E8B57')
                desc_text = f"<br>{clase['descripcion']}" if clase.get('descripcion') else ""
                aula_text = f"<br><span style='opacity:0.7'>{clase['aula']}</span>" if clase.get('aula') else ""
                dot = f"<span style='color:{color_borde}; font-size:1.1em;'>●</span>"
                
                st.markdown(f"""
                <div style='border-left: 4px solid {color_borde}; padding: 8px 12px; margin-bottom: 8px; background: rgba(255,255,255,0.03); border-radius: 0 6px 6px 0;'>
                    <strong>{clase['hora']}</strong><br>
                    {dot} {clase['asignatura']}{aula_text}{desc_text}
                </div>""", unsafe_allow_html=True)
        else:
            st.info("No hay clases ni eventos programados.")
    
    with col_tareas:
        st.subheader(f"📝 Tareas: {fecha_seleccionada.strftime('%A %d')}")
        
        tareas_hoy_list = []
        tareas_proximas_list = []
        hoy_real = get_madrid_date()

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
            # Ordenar por hora si no es día completo
            def sort_key_daily(x):
                # 1. Dia completo primero (o ultimo? mejor primero como "todo el dia") -> False (0) vs True (1)
                # 2. Hora
                is_all_day = x.get('dia_completo', True)
                hora = x.get('hora', "23:59")
                return (0 if is_all_day else 1, hora)
            
            tareas_hoy_list.sort(key=sort_key_daily)

            st.markdown("### Tareas del Día")
            for t in tareas_hoy_list:
                color = COLORES_TIPO.get(t['tipo'], "gray")
                estilo_completada = "opacity: 0.5;" if t['estado'] == 'Completada' else ""
                dot = f"<span style='color:{color}; font-size:1.1em;'>●</span>"
                
                hora_badge = ""
                if not t.get('dia_completo', True) and t.get('hora'):
                    hora_badge = f"<span style='background-color:#444; color:white; padding: 2px 6px; border-radius: 4px; font-size: 0.8em; margin-right: 5px'>{t['hora']}</span>"
                
                st.markdown(f"""
                <div style='border-left: 4px solid {color}; padding: 8px 12px; margin-bottom: 6px; background: rgba(255,255,255,0.03); border-radius: 0 6px 6px 0; {estilo_completada}'>
                    {hora_badge}{dot} <strong>{t['titulo']}</strong> <span style='background-color:{color}; padding: 2px 6px; border-radius: 4px; color: white; font-size: 0.8em'>{t['tipo']}</span>
                </div>""", unsafe_allow_html=True)
                if t['estado'] != 'Completada':
                    if st.button("Completar", key=f"d_{t['id']}", use_container_width=False):
                        t['estado'] = 'Completada'
                        gestionar_tareas('actualizar', tarea_actualizada=t)
                        st.rerun()

        # Ordenar Deadlines: 1. Importancia, 2. Dias que quedan
        def sort_deadlines(x):
            # 1. Prioridad: Urgente(0) > Importante(1) > Normal(2) > Baja(3) > Otro(4)
            prio_map = {"Urgente": 0, "Importante": 1, "Normal": 2, "Baja": 3}
            p_val = prio_map.get(x.get('prioridad'), 4)
            
            # 2. Dias Restantes
            d_val = 9999
            if x.get('fecha_fin'):
                try:
                    d_fin = datetime.strptime(x['fecha_fin'], "%Y-%m-%d").date()
                    d_val = (d_fin - hoy_real).days
                except: pass
            
            return (p_val, d_val)
        
        tareas_proximas_list.sort(key=sort_deadlines)

        if tareas_proximas_list and fecha_seleccionada == hoy_real:
            st.markdown("### Entregas y Deadlines")
            for t in tareas_proximas_list:
                color = COLORES_TIPO.get(t['tipo'], "gray")
                dot = f"<span style='color:{color}; font-size:1.1em;'>●</span>"
                estilo_completada = "opacity: 0.5;" if t['estado'] == 'Completada' else ""
                
                hora_badge = ""
                if not t.get('dia_completo', True) and t.get('hora'):
                    hora_badge = f"<span style='background-color:#444; color:white; padding: 2px 6px; border-radius: 4px; font-size: 0.8em; margin-left: 5px'>{t['hora']}</span>"
                
                st.markdown(f"""
                <div style='border-left: 4px solid {color}; padding: 8px 12px; margin-bottom: 6px; background: rgba(255,255,255,0.03); border-radius: 0 6px 6px 0; {estilo_completada}'>
                    {dot} <strong>{t['titulo']}</strong> {hora_badge} | {t['msg']}<br>
                    <span style='font-size:0.85em; opacity:0.7'>Tipo: {t['tipo']}</span>
                </div>""", unsafe_allow_html=True)
                if t['estado'] != 'Completada':
                    if st.button("Completar", key=f"d_p_{t['id']}", use_container_width=False):
                        t['estado'] = 'Completada'
                        gestionar_tareas('actualizar', tarea_actualizada=t)
                        st.rerun()

def render_vista_semanal(tareas, fecha_base, horario_dinamico, horario_clases_scraped, horario_futbol_scraped):
    # CSS HACK: Forzar layout horizontal en móvil con escalado automático
    st.markdown("""
        <style>
            /* Ajustes BASICOS para móvil (Tablet/Horizontal + Vertical) */
            @media (max-width: 900px) {
                div[data-testid="stHorizontalBlock"] {
                    width: 100% !important;
                    min-width: 0 !important;
                    flex-direction: row !important;
                    flex-wrap: nowrap !important;
                    overflow-x: hidden !important; 
                    gap: 0 !important;
                }
                div[data-testid="column"] {
                    flex: 1 1 0 !important;
                    min-width: 0 !important;
                    width: 0 !important; /* Truco para que flex funcione con min-width 0 */
                    padding: 0 !important;
                }
            }

            /* Ajustes ESPECÍFICOS VERTICAL (PORTRAIT) - CSS GRID REVOLUTION */
            @media (orientation: portrait) and (max-width: 600px) {
                 div[data-testid="stHorizontalBlock"] {
                    display: grid !important;
                    grid-template-columns: repeat(7, 1fr) !important;
                    gap: 1px !important; /* Minima separacion */
                    width: 100% !important;
                    min-width: 0 !important;
                 }
                 
                 div[data-testid="column"] {
                    width: auto !important;
                    min-width: 0 !important;
                    max-width: none !important;
                    padding: 0 !important;
                    margin: 0 !important;
                    flex: none !important; /* Desactivar flex en hijos */
                 }
                 
                 /* Limpiamos margenes texto */
                 div[data-testid="column"] p, div[data-testid="column"] div, div[data-testid="column"] strong {
                    font-size: 3.5vw !important; 
                    line-height: normal !important;
                    margin: 0 !important;
                    padding: 0 !important;
                    text-align: center !important; 
                }
                
                /* CLASE PERSONALIZADA para el Header (inyectada en el HTML abajo) */
                .mobile-header-text {
                    font-size: 3vw !important;
                    padding: 0 !important;
                    margin: 0 !important;
                    line-height: normal !important;
                }
                .mobile-header-num {
                    font-size: 3.5vw !important;
                    padding: 0 !important;
                     margin: 0 !important;
                     line-height: normal !important;
                }

                /* Botones: ICON ONLY MODE */
                div[data-testid="stButton"] button {
                    font-size: 4vw !important;
                    padding: 0px !important;
                    min-height: 25px !important;
                    height: 25px !important;
                    width: 100% !important;
                    border: none !important;
                    background-color: transparent !important;
                    margin: 0 !important;
                }
                 div[data-testid="stButton"] button p {
                    font-size: 4vw !important;
                    padding: 0 !important;
                    width: 100% !important;
                    white-space: nowrap !important;
                    overflow: hidden !important;
                    text-overflow: clip !important;
                    display: block !important;
                    max-width: 1.5em !important;
                    margin: 0 auto !important;
                }
                
                /* EXCEPCION: Restaurar layout normal dentro de los Diálogos (Popups) - FUERZA VERTICAL */
                div[data-testid="stDialog"] div[data-testid="stHorizontalBlock"] {
                    display: flex !important;
                    flex-direction: column !important; /* APILAR EN VERTICAL */
                    gap: 5px !important; 
                }
                
                div[data-testid="stDialog"] div[data-testid="column"] {
                    width: 100% !important;
                    flex: none !important;
                    min-width: 0 !important;
                }
            }
        }
        </style>
    """, unsafe_allow_html=True)

    # --- NAVEGACIÓN SEMANAL CON FLECHAS ---
    nav_w1, nav_w2, nav_w3 = st.columns([1, 3, 1])
    start_of_week = fecha_base - timedelta(days=fecha_base.weekday())
    end_of_week = start_of_week + timedelta(days=6)
    with nav_w1:
        if st.button("◀ Semana anterior", key="prev_week", use_container_width=True):
            new_d = fecha_base - timedelta(weeks=1)
            st.session_state["fecha_base_manual"] = new_d
            st.session_state["date_input_sidebar"] = new_d
            st.rerun()
    with nav_w2:
        st.markdown(f"<h3 style='text-align:center; margin:0;'>{start_of_week.day}/{start_of_week.month} — {end_of_week.day}/{end_of_week.month}/{end_of_week.year}</h3>", unsafe_allow_html=True)
    with nav_w3:
        if st.button("Semana siguiente ▶", key="next_week", use_container_width=True):
            new_d = fecha_base + timedelta(weeks=1)
            st.session_state["fecha_base_manual"] = new_d
            st.session_state["date_input_sidebar"] = new_d
            st.rerun()
    
    cols = st.columns(7)
    dias_semana_lbl = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
    
    for i, col in enumerate(cols):
        dia_actual = start_of_week + timedelta(days=i)
        is_today = dia_actual == get_madrid_date()
        is_selected = dia_actual == fecha_base
        
        # Estilo Header
        if is_selected:
            header_bg = "#1E90FF"
            header_border = "3px solid #1E90FF"
            text_color = "white"
        elif is_today:
            header_bg = "#FF4B4B"
            header_border = "3px solid #FF4B4B"
            text_color = "white"
        else:
            header_bg = "transparent" # o gris oscuro
            header_border = "1px solid #444"
            text_color = "var(--text-color)"
            
        with col:
            # Header
            # Header con Clases Custom para CSS targeting
            st.markdown(f"""
            <div style='text-align: center; border-bottom: {header_border}; margin-bottom:5px;'>
                <div style='background-color: {header_bg}; color: {text_color}; border-radius: 4px 4px 0 0; padding: 2px;'>
                    <strong class="mobile-header-text">{dias_semana_lbl[i]}</strong>
                </div>
                <div class="mobile-header-num" style='font-size:1.2em; padding: 5px;'>{dia_actual.day}</div>
            </div>""", unsafe_allow_html=True)
            
            # --- RECOLECCIÓN DE ITEMS ---
            items_visuales = []
            
            # 1. Horario Universitario Scrapeado
            dia_str = str(dia_actual)
            for c in horario_clases_scraped:
                if c['fecha'] == dia_str:
                     items_visuales.append({
                         "tipo": "Clase",
                         "titulo": c['asignatura'],
                         "hora_sort": c['hora'].split('-')[0].strip(),
                         "hora": c['hora'],
                         "aula": c['aula'],
                         "color": "#2E8B57",
                         "es_universidad": True,
                         "fecha": c['fecha'],
                         "raw": c 
                     })
             
            # 1.5 Futbol
            for f in horario_futbol_scraped:
                if f['fecha'] == dia_str:
                    items_visuales.append({
                        "tipo": "Futbol",
                        "titulo": f['titulo'],
                        "hora_sort": f['hora'] if f['hora'] else "00:00",
                        "hora": f['hora'] if f['hora'] else "TBD",
                        "aula": f['aula'],
                        "color": "#FF4B4B",
                        "es_futbol": True,
                        "raw": f
                    })

            # 2. Horario Dinamico
            for item in horario_dinamico:
                es_este_dia = False
                if item.get('es_rutina'):
                     if i in item.get('dias_semana', []): es_este_dia = True
                elif item.get('es_multidia') and item.get('fecha') and item.get('fecha_fin_evento'):
                     try:
                         f_ini_w = datetime.strptime(item['fecha'], "%Y-%m-%d").date()
                         f_fin_w = datetime.strptime(item['fecha_fin_evento'], "%Y-%m-%d").date()
                         if f_ini_w <= dia_actual <= f_fin_w: es_este_dia = True
                     except: pass
                else:
                     if item.get('fecha') == dia_str: es_este_dia = True
                
                if es_este_dia:
                    hora_sort_val = item.get('hora_inicio', '00:00') or '00:00'
                    hora_display_w = "Todo el día"
                    if not item.get('dia_completo') and item.get('hora_inicio') and item.get('hora_fin'):
                        hora_display_w = f"{item['hora_inicio']} - {item['hora_fin']}"
                    
                    titulo_w = item['titulo']
                    
                    items_visuales.append({
                        "tipo": "Evento",
                        "titulo": titulo_w,
                        "hora_sort": hora_sort_val,
                        "hora": hora_display_w,
                        "ubicacion": item.get('ubicacion'),
                        "color": item.get('color', '#1E90FF'),
                        "es_rutina": item.get('es_rutina'),
                        "es_multidia": item.get('es_multidia'),
                        "id": item.get('id'),
                        "dias_semana": item.get('dias_semana'),
                        "raw": item
                    })
            
            # 3. Tareas
            for t in tareas:
                if t.get('estado') == 'Completada': continue
                
                fecha_t = t.get('fecha')
                fecha_f = t.get('fecha_fin')
                
                hora_str = t.get('hora', "23:59")
                if t.get('dia_completo'): hora_str = "00:00"
                if not hora_str: hora_str = "23:59"
                
                es_deadline = False
                
                if fecha_t == str(dia_actual) and not fecha_f:
                    pass
                elif fecha_f == str(dia_actual):
                    es_deadline = True
                else:
                   continue
                
                items_visuales.append({
                     "tipo": "tarea",
                     "titulo": t['titulo'],
                     "hora_sort": hora_str,
                     "hora": t.get('hora'),
                     "dia_completo": t.get('dia_completo'),
                     "color": COLORES_TIPO.get(t.get('tipo', 'Otro'), '#808080'),
                     "es_deadline": es_deadline,
                     "prioridad": t.get('prioridad'),
                     "estado": t.get('estado'),
                     "id": t['id'],
                     "raw": t
                })

            # Ordenar
            def get_sort_key(x):
                try: return x['hora_sort'].replace(":", "")
                except: return "9999"
            
            items_visuales.sort(key=get_sort_key)
            
            # PINTAR ITEMS
            for item in items_visuales:
                item_color = item.get('color', '#808080')
                hora_inicio = item.get('hora_sort', '')
                trunc_title = (item['titulo'][:10] + '..') if len(item['titulo']) > 10 else item['titulo']
                label = f"● {hora_inicio} {trunc_title}"
                
                # Key unica
                try:
                    safe_id = str(item.get('id', item['titulo'])).replace(" ", "_")
                except: safe_id = "uniq"

                key_btn = f"btn_w_{i}_{safe_id}_{item['hora_sort']}"
                
                if st.button(label, key=key_btn, use_container_width=True):
                    if 'titulo' not in item['raw']: item['raw']['titulo'] = item['titulo']
                    mostrar_detalle_item(item['raw'])


# --- CONSTANTES DE FECHA (ESPAÑOL) ---
NOMBRES_MESES = {
    1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril", 5: "Mayo", 6: "Junio",
    7: "Julio", 8: "Agosto", 9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre"
}
DIAS_SEMANA_ABR = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]

def render_vista_mensual(tareas, fecha_base, horario_dinamico, horario_clases_scraped, horario_futbol_scraped):
    # CSS HACK force horizontal
    st.markdown("""
        <style>
            /* Ajustes PORTRAIT MENSUAL - CSS GRID */
            @media (orientation: portrait) and (max-width: 600px) {
                 div[data-testid="stHorizontalBlock"] {
                    display: grid !important;
                    grid-template-columns: repeat(7, 1fr) !important;
                    gap: 1px !important;
                    width: 100% !important;
                 }
                  div[data-testid="column"] {
                    width: auto !important;
                    min-width: 0 !important;
                    max-width: none !important;
                    padding: 0 !important;
                    margin: 0 !important;
                    flex: none !important;
                 }
                
                 div[data-testid="stButton"] button {
                    padding: 0px !important;
                    background-color: transparent !important; 
                    border: none !important;
                    min-height: 20px !important;
                    height: 20px !important;
                    margin: 0 !important;
                }
                 div[data-testid="stButton"] button p {
                    font-size: 4vw !important;
                    padding: 0 !important;
                    width: 100% !important;
                    white-space: nowrap !important;
                    overflow: hidden !important;
                    text-overflow: clip !important;
                    display: block !important;
                    max-width: 1.5em !important;
                    margin: 0 auto !important;
                }
                div[data-testid="column"] div[data-testid="stMarkdown"] p {
                     font-size: 2.5vw !important;
                     margin: 0 !important;
                     padding: 0 !important;
                     text-align: center !important;
                }
                
                /* EXCEPCION: Restaurar layout normal dentro de los Diálogos (Popups) */
                div[data-testid="stDialog"] div[data-testid="stHorizontalBlock"] {
                    display: flex !important;
                    gap: 10px !important;
                    grid-template-columns: none !important;
                }
                div[data-testid="stDialog"] div[data-testid="column"] {
                    flex: 1 !important;
                    width: auto !important;
                    max-width: none !important;
                    min-width: 0 !important;
                }
            }
        }
        </style>
    """, unsafe_allow_html=True)

    nombre_mes = NOMBRES_MESES.get(fecha_base.month, "Mes")
    
    # --- NAVEGACIÓN MENSUAL CON FLECHAS ---
    nav_m1, nav_m2, nav_m3 = st.columns([1, 3, 1])
    with nav_m1:
        if st.button("◀ Mes anterior", key="prev_month", use_container_width=True):
            if fecha_base.month == 1:
                new_date = fecha_base.replace(year=fecha_base.year - 1, month=12, day=1)
            else:
                new_date = fecha_base.replace(month=fecha_base.month - 1, day=1)
            st.session_state["fecha_base_manual"] = new_date
            st.session_state["date_input_sidebar"] = new_date
            st.rerun()
    with nav_m2:
        st.markdown(f"<h3 style='text-align:center; margin:0;'>{nombre_mes} {fecha_base.year}</h3>", unsafe_allow_html=True)
    with nav_m3:
        if st.button("Mes siguiente ▶", key="next_month", use_container_width=True):
            if fecha_base.month == 12:
                new_date = fecha_base.replace(year=fecha_base.year + 1, month=1, day=1)
            else:
                new_date = fecha_base.replace(month=fecha_base.month + 1, day=1)
            st.session_state["fecha_base_manual"] = new_date
            st.session_state["date_input_sidebar"] = new_date
            st.rerun()
    
    calendar.setfirstweekday(calendar.MONDAY)
    cal = calendar.monthcalendar(fecha_base.year, fecha_base.month)
    
    # Cabecera (ELIMINADO A PETICIÓN DE USUARIO)
    # cols_header = st.columns(7)
    # for i, d in enumerate(DIAS_SEMANA_ABR):
    #     cols_header[i].markdown(f"<div style='text-align:center; background-color: #262730; padding: 5px; border-radius: 4px; margin-bottom: 5px;'><strong>{d}</strong></div>", unsafe_allow_html=True)

        
    for week in cal:
        cols = st.columns(7)
        for i, day_num in enumerate(week):
            with cols[i]:
                if day_num == 0:
                    st.markdown("<div style='min-height:80px;'></div>", unsafe_allow_html=True)
                    continue
                
                dia_actual = date(fecha_base.year, fecha_base.month, day_num)
                is_today = dia_actual == get_madrid_date()
                is_selected = dia_actual == fecha_base
                
                # --- HEADERS DIA ---
                border_style = "1px solid #444"
                num_color = "#AAA"
                
                if is_today:
                    border_style = "2px solid #FF4B4B"
                    num_color = "#FF4B4B"
                elif is_selected:
                    border_style = "2px solid #1E90FF"
                    num_color = "#1E90FF"
                
                st.markdown(f"<div style='text-align: right; font-weight: bold; border-bottom: {border_style}; margin-bottom: 4px; color: {num_color};'>{day_num} <span style='font-size:0.75em; opacity:0.7; font-weight:normal'>{DIAS_SEMANA_ABR[i]}</span></div>", unsafe_allow_html=True)
                
                # --- RECOLECCIÓN DE ITEMS ---
                items_visuales = []
                dia_str = str(dia_actual)
                
                # 1. Clases Scrapeadas
                for c in horario_clases_scraped:
                     if c['fecha'] == dia_str:
                        items_visuales.append({
                            "tipo": "Clase",
                            "titulo": c['asignatura'],
                            "hora_sort": c['hora'].split('-')[0].strip(),
                            "hora": c['hora'],
                            "aula": c['aula'],
                            "color": "#2E8B57",
                            "es_universidad": True,
                            "fecha": c['fecha'],
                            "raw": c
                        })

                # 1.5 Futbol
                for f in horario_futbol_scraped:
                    if f['fecha'] == dia_str:
                         items_visuales.append({
                            "tipo": "Futbol",
                            "titulo": f['titulo'],
                            "hora_sort": f['hora'] if f['hora'] else "00:00",
                            "hora": f['hora'] if f['hora'] else "TBD",
                            "aula": f['aula'],
                            "color": "#FF4B4B",
                            "es_futbol": True,
                            "raw": f
                         })

                # 2. Horario Dinamico
                for item in horario_dinamico:
                    es_este_dia_m = False
                    if item.get('es_rutina'):
                         if i in item.get('dias_semana', []): es_este_dia_m = True
                    elif item.get('es_multidia') and item.get('fecha') and item.get('fecha_fin_evento'):
                         try:
                             f_ini_m2 = datetime.strptime(item['fecha'], "%Y-%m-%d").date()
                             f_fin_m2 = datetime.strptime(item['fecha_fin_evento'], "%Y-%m-%d").date()
                             if f_ini_m2 <= dia_actual <= f_fin_m2: es_este_dia_m = True
                         except: pass
                    else:
                         if item.get('fecha') == dia_str: es_este_dia_m = True
                    
                    if es_este_dia_m:
                        hora_sort_m = item.get('hora_inicio', '00:00') or '00:00'
                        hora_display_m = "Todo el día"
                        if not item.get('dia_completo') and item.get('hora_inicio') and item.get('hora_fin'):
                            hora_display_m = f"{item['hora_inicio']} - {item['hora_fin']}"
                        
                        titulo_m = item['titulo']
                        
                        items_visuales.append({
                            "tipo": "Evento",
                            "titulo": titulo_m,
                            "hora_sort": hora_sort_m,
                            "hora": hora_display_m,
                            "ubicacion": item.get('ubicacion'),
                            "color": item.get('color', '#1E90FF'),
                            "es_rutina": item.get('es_rutina'),
                            "es_multidia": item.get('es_multidia'),
                            "id": item.get('id'),
                            "dias_semana": item.get('dias_semana'),
                            "raw": item
                        })
                
                # 3. Tareas
                for t in tareas:
                    if t.get('estado') == 'Completada': continue
                    fecha_t = t.get('fecha')
                    fecha_f = t.get('fecha_fin')
                    
                    if fecha_t == dia_str and not fecha_f:
                        pass
                    elif fecha_f == dia_str:
                        pass
                    else:
                        continue 

                    items_visuales.append({
                         "tipo": "tarea",
                         "titulo": t['titulo'],
                         "hora_sort": t.get('hora', "23:59"),
                         "hora": t.get('hora'),
                         "color": COLORES_TIPO.get(t.get('tipo', 'Otro'), '#808080'),
                         "msg": t.get('msg'),
                         "prioridad": t.get('prioridad'),
                         "estado": t.get('estado'),
                         "id": t['id'],
                         "raw": t
                    })

                items_visuales.sort(key=lambda x: x['hora_sort'].replace(":", "") if x['hora_sort'] else "9999")
                
                # RENDER DE BOTONES
                for item in items_visuales:
                    title_full = item['titulo']
                    hora_inicio_m = item.get('hora_sort', '')
                    trunc_m = (title_full[:6] + '..') if len(title_full) > 6 else title_full
                    
                    if item['tipo'] == 'Clase':
                        label_m = f"● {hora_inicio_m} {trunc_m}"
                    else:
                        label_m = f"● {trunc_m}"
                    
                    # Key única mensual
                    try: 
                        s_id = str(item.get('id', item['titulo'])).replace(" ", "")
                    except: s_id = "u"
                    key_m = f"btn_m_{day_num}_{s_id}_{item['hora_sort']}"
                    
                    if st.button(label_m, key=key_m, help=f"{item['hora_sort']} - {title_full}", use_container_width=True):
                        if 'titulo' not in item['raw']: item['raw']['titulo'] = item['titulo']
                        mostrar_detalle_item(item['raw'])


if __name__ == "__main__":
    main()
