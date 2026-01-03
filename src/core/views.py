from django.shortcuts import render, get_object_or_404
from .models import Estacion, LecturaEstacion, Captura 
import json, math
from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import Sum, Avg
from django.utils import timezone
from django.urls import reverse 
import datetime
from datetime import timedelta

def lista_estaciones(request):
    """
    Portada: Lista de estaciones + Gráfico Global de la ciudad.
    """
    estaciones = Estacion.objects.all().order_by('id_externo')
    
    # 2. DATOS GLOBALES (Últimas 24h EXACTAS)
    desde = timezone.now() - timedelta(hours=24)
    
    # Optimizamos: traemos solo timestamp e id para no cargar memoria
    capturas_recientes = Captura.objects.filter(
        timestamp__gte=desde
    ).order_by('timestamp')
    
    datos_globales = []
    
    for c in capturas_recientes:
        # Sumamos bicis. 
        # NOTA: Esto hace 1 query por captura. Si tienes 380 capturas, son 380 queries.
        # Para producción idealmente usaríamos 'annotate', pero mantenemos tu lógica por seguridad.
        total_bicis = c.lecturas.aggregate(total=Sum('bicis_disponibles'))['total']
        
        if total_bicis is not None:
            datos_globales.append({
                'x': c.timestamp.isoformat(),
                'y': total_bicis
            })

    context = {
        'estaciones': estaciones,
        'datos_globales': json.dumps(datos_globales, cls=DjangoJSONEncoder)
    }
    return render(request, 'core/lista_estaciones.html', context)

def detalle_estacion(request, estacion_id):
    estacion = get_object_or_404(Estacion, id_externo=estacion_id)
    
    # 1. GESTIÓN DEL RANGO TEMPORAL
    # Leemos el parámetro GET. Por defecto '24h'.
    rango = request.GET.get('rango', '24h')
    
    if rango == '7d':
        horas_atras = 24 * 7 # 168 horas
        titulo_rango = "Últimos 7 días"
    else:
        horas_atras = 24
        titulo_rango = "Últimas 24 horas"
        rango = '24h' # Forzamos valor limpio por seguridad

    start_date = timezone.now() - timedelta(hours=horas_atras)

    # 2. CONSULTA FILTRADA POR ESE RANGO
    lecturas_query = LecturaEstacion.objects.filter(
        estacion=estacion,
        captura__timestamp__gte=start_date
    ).select_related('captura').order_by('captura__timestamp')
    
    lecturas = list(lecturas_query)
    
    # --- PROCESAMIENTO DE DATOS ---
    dataset_bicis = []
    dataset_anclajes = []
    
    suma_bicis = 0
    suma_anclajes = 0
    conteo_sin_bicis = 0
    conteo_sin_anclajes = 0
    total = len(lecturas)
    
    for l in lecturas:
        ts = l.captura.timestamp.isoformat()
        dataset_bicis.append({'x': ts, 'y': l.bicis_disponibles})
        dataset_anclajes.append({'x': ts, 'y': l.anclajes_libres})
        
        suma_bicis += l.bicis_disponibles
        suma_anclajes += l.anclajes_libres
        
        if l.bicis_disponibles == 0: conteo_sin_bicis += 1
        if l.anclajes_libres == 0: conteo_sin_anclajes += 1

    # --- ESTADÍSTICAS (Calculadas sobre el rango seleccionado) ---
    stats = {
        'media_bicis': 0,
        'media_anclajes': 0,
        'pct_sin_bicis': 0,    
        'pct_sin_anclajes': 0, 
    }

    if total > 0:
        stats['media_bicis'] = round(suma_bicis / total, 1)
        stats['media_anclajes'] = round(suma_anclajes / total, 1)
        stats['pct_sin_bicis'] = round((conteo_sin_bicis / total) * 100, 1)
        stats['pct_sin_anclajes'] = round((conteo_sin_anclajes / total) * 100, 1)

    # --- MAPA DE CALOR (Siempre últimos 30 días para contexto histórico) ---
    hace_un_mes = timezone.now() - timedelta(days=30)
    lecturas_mes = LecturaEstacion.objects.filter(
        estacion=estacion, 
        captura__timestamp__gte=hace_un_mes
    ).select_related('captura').only('captura__timestamp', 'bicis_disponibles')
    
    # Inicializamos matriz: 7 días x 24 horas x 4 cuartos
    # Cada cuarto es un dict: {'s': suma, 'c': conteo}
    heatmap_raw = [[[{'s': 0, 'c': 0} for _ in range(4)] for _ in range(24)] for _ in range(7)]

    for l in lecturas_mes:
        fl = timezone.localtime(l.captura.timestamp)
        dia = fl.weekday()
        hora = fl.hour
        # Calculamos el cuarto de hora (0, 1, 2 o 3)
        cuarto = fl.minute // 15
        
        heatmap_raw[dia][hora][cuarto]['s'] += l.bicis_disponibles
        heatmap_raw[dia][hora][cuarto]['c'] += 1

    dias_nombres = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom']
    heatmap_data = []

    for i in range(7):
        fila_horas = []
        for h in range(24):
            bloque_cuartos = []
            for q in range(4):
                datos = heatmap_raw[i][h][q]
                if datos['c'] > 0:
                    promedio = round(datos['s'] / datos['c'], 1)
                else:
                    promedio = None
                bloque_cuartos.append(promedio)
            
            # Ahora cada celda 'h' contiene una lista de 4 promedios
            fila_horas.append(bloque_cuartos)
            
        heatmap_data.append({
            'nombre': dias_nombres[i], 
            'horas': fila_horas
        })

    context = {
        'estacion': estacion,
        'lecturas': list(reversed(lecturas[-10:])), # Lista invertida de los últimos 10
        'dataset_bicis': dataset_bicis,
        'dataset_anclajes': dataset_anclajes,
        'stats': stats, 
        'heatmap_data': heatmap_data,
        'rango_actual': rango,
        'titulo_rango': titulo_rango
    }
    return render(request, 'core/detalle_estacion.html', context)


def mapa_estaciones(request):
    """
    Mapa animado ULTRA OPTIMIZADO.
    Separa datos estáticos de dinámicos y reduce la resolución temporal.
    """
    hace_24h = timezone.now() - timedelta(hours=24)
    
    # 1. DATOS ESTÁTICOS (Se envían 1 sola vez)
    # Diccionario: { id_externo: { lat, lon, nombre, url } }
    estaciones_objs = Estacion.objects.all()
    estaciones_static = {}
    
    for e in estaciones_objs:
        estaciones_static[e.id_externo] = {
            'lat': float(e.latitud),
            'lon': float(e.longitud),
            'nombre': e.nombre,
            'url': reverse('detalle_estacion', args=[e.id_externo])
        }

    # 2. DATOS DINÁMICOS (Capturas)
    # Filtramos últimas 24h
    capturas_qs = Captura.objects.filter(
        timestamp__gte=hace_24h
    ).order_by('timestamp')
    
    # OPTIMIZACIÓN A: Sampling (Tomar 1 de cada 2 para reducir carga a la mitad)
    # Si tienes muchos datos, el ojo humano no distingue cambios cada 3 min en un mapa rápido.
    # [::2] significa "coge el 0, el 2, el 4..."
    capturas = list(capturas_qs)[::2] 
    
    timeline_data = []
    
    for c in capturas:
        fecha_local = timezone.localtime(c.timestamp)
        
        # OPTIMIZACIÓN B: Values List (Mucho más rápido que objetos)
        # Solo traemos los enteros necesarios: Estación ID, Bicis, Anclajes
        lecturas_data = c.lecturas.values_list(
            'estacion__id_externo', 
            'bicis_disponibles', 
            'anclajes_libres'
        )
        
        # Convertimos la QuerySet a un diccionario ligero para JS
        # Formato: { '1': [10, 5], '2': [0, 20] ... } -> ID: [Bicis, Anclajes]
        lecturas_dict = {
            str(item[0]): [item[1], item[2]] 
            for item in lecturas_data
        }
            
        timeline_data.append({
            'ts': fecha_local.strftime("%H:%M"), # Hora legible
            'd': lecturas_dict                   # Datos comprimidos
        })

    context = {
        # Pasamos los dos bloques de datos por separado
        'estaciones_static': json.dumps(estaciones_static, cls=DjangoJSONEncoder),
        'timeline_json': json.dumps(timeline_data, cls=DjangoJSONEncoder)
    }
    return render(request, 'core/mapa_estaciones.html', context)

# --- LÓGICA DEL ORÁCULO ---

def calcular_prediccion_precisa(estacion_id, dia_semana, hora, minuto):
    """
    Algoritmo de 'Micro-Ventana':
    Analiza exclusivamente el registro solicitado y sus vecinos inmediatos (±4 min)
    de los últimos 60 días. Calcula media y tendencia.
    """
    # 1. Definir la ventana de tiempo (Target ± 4 min)
    # Usamos una fecha dummy arbitraria para poder operar con tiempos
    dummy_date = datetime.datetime(2000, 1, 1, hora, minuto)
    start_time = (dummy_date - timedelta(minutes=4)).time()
    end_time = (dummy_date + timedelta(minutes=4)).time()

    # 2. Filtrar histórico (Últimos 60 días)
    hace_dos_meses = timezone.now() - timedelta(days=60)
    
    # Obtenemos TODOS los registros que caen en esa micro-ventana
    qs = LecturaEstacion.objects.filter(
        estacion__id_externo=estacion_id,
        captura__timestamp__gte=hace_dos_meses,
        captura__timestamp__week_day=dia_semana,
        captura__timestamp__time__range=(start_time, end_time)
    )

    if not qs.exists():
        return None

    # 3. CÁLCULO DE MEDIAS
    stats = qs.aggregate(
        promedio_bicis=Avg('bicis_disponibles'),
        promedio_anclajes=Avg('anclajes_libres')
    )
    
    media_b = round(stats['promedio_bicis'] or 0, 1)
    media_a = round(stats['promedio_anclajes'] or 0, 1)

    # 4. CÁLCULO DE TENDENCIA
    # Comparamos el promedio ANTES del minuto target vs DESPUÉS
    antes = qs.filter(captura__timestamp__time__lt=dummy_date.time()).aggregate(m=Avg('bicis_disponibles'))['m'] or media_b
    despues = qs.filter(captura__timestamp__time__gt=dummy_date.time()).aggregate(m=Avg('bicis_disponibles'))['m'] or media_b
    
    diff = despues - antes
    
    if diff > 0.3:
        tendencia = "Subiendo 📈" # Se está llenando
    elif diff < -0.3:
        tendencia = "Bajando 📉" # Se está vaciando
    else:
        tendencia = "Estable 😐"

    # 5. SEMÁFORO DE PROBABILIDAD (Umbral de seguridad: 5 bicis/huecos)
    # Si hay > 5, es 100% seguro. Si hay 0, es 0%.
    prob_bici = min(100, int((media_b / 5.0) * 100))
    prob_hueco = min(100, int((media_a / 5.0) * 100))

    return {
        'prob_bici': prob_bici,
        'prob_hueco': prob_hueco,
        'media_bicis': media_b,
        'media_anclajes': media_a,
        'tendencia': tendencia
    }

import math
# ... otros imports ...

# --- FUNCIÓN AUXILIAR: CALCULAR DISTANCIA (Haversine) ---
def haversine(lat1, lon1, lat2, lon2):
    """Devuelve distancia en metros entre dos coordenadas."""
    R = 6371000  # Radio Tierra en metros
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = math.sin(dphi/2)**2 + \
        math.cos(phi1) * math.cos(phi2) * \
        math.sin(dlambda/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c

def planificador(request):
    estaciones = Estacion.objects.all().order_by('nombre')
    resultado = None
    
    if 'origen' in request.GET and 'destino' in request.GET:
        try:
            origen_id = request.GET.get('origen')
            destino_id = request.GET.get('destino')
            
            # Recuperamos objetos Estacion completos (necesitamos lat/lon)
            obj_origen = Estacion.objects.get(id_externo=origen_id)
            obj_destino = Estacion.objects.get(id_externo=destino_id)

            # --- INPUTS DE TIEMPO ---
            dia_input = int(request.GET.get('dia')) # Django format: 1=Dom...7=Sab
            hora_input = int(request.GET.get('hora'))
            min_input = int(request.GET.get('minuto', 0))

            # --- 1. CÁLCULO DE VIAJE ---
            # Distancia aérea
            dist_metros = haversine(
                float(obj_origen.latitud), float(obj_origen.longitud),
                float(obj_destino.latitud), float(obj_destino.longitud)
            )
            
            # Estimación Realista:
            # Factor 1.4 por callejeo (Manhattan/Tortuosidad)
            # Velocidad media Bizi: 12km/h = 200 metros/minuto
            dist_real = dist_metros * 1.4
            minutos_viaje = int(dist_real / 200)
            
            # Mínimo 5 min (nadie teletransporta) si es muy cerca
            if minutos_viaje < 5: minutos_viaje = 5

            # --- 2. CÁLCULO HORA LLEGADA ---
            # Usamos datetime para sumar minutos fácilmente y manejar cambios de día
            # Creamos una fecha dummy. Nota: Django week_day 1=Dom es raro para Python.
            # Simplemente sumamos minutos y extraemos la nueva hora.
            
            # Referencia base arbitraria
            fecha_salida = datetime.datetime(2024, 1, 1, hora_input, min_input)
            fecha_llegada = fecha_salida + timedelta(minutes=minutos_viaje)
            
            hora_llegada = fecha_llegada.hour
            min_llegada = fecha_llegada.minute
            
            # Detectar cambio de día (si la fecha cambió)
            dia_llegada = dia_input
            if fecha_llegada.day != fecha_salida.day:
                dia_llegada += 1
                if dia_llegada > 7: dia_llegada = 1 # Vuelta a Domingo

            # --- 3. ORÁCULO INTELIGENTE ---
            
            # A. Origen: A la hora de SALIDA
            datos_origen = calcular_prediccion_precisa(origen_id, dia_input, hora_input, min_input)
            
            # B. Destino: A la hora de LLEGADA
            datos_destino = calcular_prediccion_precisa(destino_id, dia_llegada, hora_llegada, min_llegada)
            
            # Manejo de vacíos
            if not datos_origen: datos_origen = {'prob_bici': 0, 'media_bicis': 0, 'tendencia': 'Sin datos'}
            if not datos_destino: datos_destino = {'prob_hueco': 0, 'media_anclajes': 0, 'tendencia': 'Sin datos'}

            resultado = {
                'viaje': {
                    'minutos': minutos_viaje,
                    'distancia_km': round(dist_real / 1000, 1),
                    'hora_salida': f"{hora_input:02d}:{min_input:02d}",
                    'hora_llegada': f"{hora_llegada:02d}:{min_llegada:02d}",
                    'cambio_dia': (dia_llegada != dia_input)
                },
                'origen': {
                    'nombre': obj_origen.nombre,
                    'pct': datos_origen['prob_bici'],
                    'media': datos_origen['media_bicis'],
                    'tendencia': datos_origen.get('tendencia', '-'),
                    'color': 'success' if datos_origen['prob_bici'] > 60 else 'warning' if datos_origen['prob_bici'] > 20 else 'danger'
                },
                'destino': {
                    'nombre': obj_destino.nombre,
                    'pct': datos_destino['prob_hueco'],
                    'media': datos_destino['media_anclajes'],
                    'tendencia': datos_destino.get('tendencia', '-'),
                    'color': 'success' if datos_destino['prob_hueco'] > 60 else 'warning' if datos_destino['prob_hueco'] > 20 else 'danger'
                }
            }
        except Exception as e:
            print(f"Error planificador: {e}")
            pass

    context = {
        'estaciones': estaciones,
        'resultado': resultado,
        'form_data': request.GET 
    }
    return render(request, 'core/planificador.html', context)