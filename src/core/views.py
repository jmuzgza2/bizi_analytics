from django.shortcuts import render, get_object_or_404
from .models import Estacion, LecturaEstacion, Captura 
import json
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
    
    # --- CAMBIO CRÍTICO: FILTRAR POR TIEMPO, NO POR CANTIDAD ---
    # Calculamos el momento exacto hace 24 horas
    hace_24h = timezone.now() - timedelta(hours=24)

    # Obtenemos TODAS las lecturas de las últimas 24h
    # No importa si se capturaron cada 3 min o cada 15 min, las traerá todas.
    lecturas_query = LecturaEstacion.objects.filter(
        estacion=estacion,
        captura__timestamp__gte=hace_24h
    ).select_related('captura').order_by('captura__timestamp')
    
    # Ya no hacemos slicing [-200:], usamos todo el query
    lecturas = list(lecturas_query)
    
    # --- 1. PREPARACIÓN DE DATOS ---
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
        
        if l.bicis_disponibles == 0:
            conteo_sin_bicis += 1
        
        if l.anclajes_libres == 0:
            conteo_sin_anclajes += 1

    # --- 2. CÁLCULO DE MÉTRICAS ---
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

    ### MAPA DE CALOR (Esto sigue igual, últimos 30 días)
    hace_un_mes = timezone.now() - timedelta(days=30)
    
    lecturas_mes = LecturaEstacion.objects.filter(
        estacion=estacion,
        captura__timestamp__gte=hace_un_mes
    ).select_related('captura').only('captura__timestamp', 'bicis_disponibles')

    # Estructura de celda: {'suma': 0, 'conteo': 0}
    heatmap_raw = [[{'s': 0, 'c': 0} for _ in range(24)] for _ in range(7)]

    for l in lecturas_mes:
        # Convertimos a hora local
        # IMPORTANTE: Asegúrate que TIME_ZONE = 'Europe/Madrid' en settings.py
        fecha_local = timezone.localtime(l.captura.timestamp)
        
        dia = fecha_local.weekday() 
        hora = fecha_local.hour
        
        heatmap_raw[dia][hora]['s'] += l.bicis_disponibles
        heatmap_raw[dia][hora]['c'] += 1

    dias_nombres = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom']
    heatmap_data = []

    for i in range(7):
        fila_horas = []
        for h in range(24):
            datos = heatmap_raw[i][h]
            if datos['c'] > 0:
                promedio = round(datos['s'] / datos['c'], 1)
            else:
                promedio = None 
            fila_horas.append(promedio)
            
        heatmap_data.append({
            'nombre': dias_nombres[i],
            'horas': fila_horas
        })

    context = {
        'estacion': estacion,
        'lecturas': reversed(lecturas[-10:]), # Tabla inferior: solo las 10 últimas lecturas
        'dataset_bicis': dataset_bicis,
        'dataset_anclajes': dataset_anclajes,
        'stats': stats, 
        'heatmap_data': heatmap_data,
        # Pasamos los filtros de vuelta si los tuvieras implementados
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