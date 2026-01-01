from django.shortcuts import render, get_object_or_404
from .models import Estacion, LecturaEstacion, Captura 
import json
from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import Sum
from django.utils import timezone
import datetime
from datetime import timedelta

 


def lista_estaciones(request):
    """
    Portada: Lista de estaciones + Gráfico Global de la ciudad.
    """
    # 1. Lista de estaciones (como antes)
    estaciones = Estacion.objects.all().order_by('id_externo')
    
    # 2. DATOS GLOBALES (Últimas 24h)
    # Buscamos capturas de las últimas 24h
    desde = timezone.now() - datetime.timedelta(hours=24)
    capturas_recientes = Captura.objects.filter(timestamp__gte=desde).order_by('timestamp')
    
    # Agrupamos: Para cada captura, sumamos las bicis de todas sus lecturas
    # Esto nos da la "cantidad de bicis aparcadas en toda la ciudad" minuto a minuto
    datos_globales = []
    
    # Nota: Esta iteración se puede optimizar con 'annotate' pero vamos a lo seguro primero
    for c in capturas_recientes:
        # Sumamos bicis disponibles de esta captura concreta
        total_bicis = c.lecturas.aggregate(total=Sum('bicis_disponibles'))['total']
        
        # Si la captura falló y no tiene lecturas, total será None
        if total_bicis is not None:
            datos_globales.append({
                'x': c.timestamp.isoformat(),
                'y': total_bicis
            })

    context = {
        'estaciones': estaciones,
        'datos_globales': json.dumps(datos_globales, cls=DjangoJSONEncoder) # Pasamos el JSON
    }
    return render(request, 'core/lista_estaciones.html', context)

def detalle_estacion(request, estacion_id):
    estacion = get_object_or_404(Estacion, id_externo=estacion_id)
    
    # Obtenemos datos cronológicos. 
    # Limitamos a 288 (aprox 24h si capturamos cada 5 min) para que el gráfico sea legible
    lecturas_query = LecturaEstacion.objects.filter(
        estacion=estacion
    ).select_related('captura').order_by('captura__timestamp')
    
    # Convertimos a lista para poder iterar sin consultar la BD varias veces
    # Tomamos las últimas 200 lecturas para el análisis
    lecturas = list(lecturas_query)[-200:]
    
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
        
        # Datos para Chart.js {x, y}
        dataset_bicis.append({'x': ts, 'y': l.bicis_disponibles})
        dataset_anclajes.append({'x': ts, 'y': l.anclajes_libres})
        
        # Cálculos estadísticos
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
        'pct_sin_bicis': 0,    # Estación Vacía (Peligro para el usuario que busca bici)
        'pct_sin_anclajes': 0, # Estación Llena (Peligro para el usuario que quiere aparcar)
    }

    if total > 0:
        stats['media_bicis'] = round(suma_bicis / total, 1)
        stats['media_anclajes'] = round(suma_anclajes / total, 1)
        stats['pct_sin_bicis'] = round((conteo_sin_bicis / total) * 100, 1)
        stats['pct_sin_anclajes'] = round((conteo_sin_anclajes / total) * 100, 1)



    ### MAPA DE CALOR 

    # Analizamos solo los últimos 30 días para que sea representativo
    hace_un_mes = timezone.now() - timedelta(days=30)
    
    # Optimizamos la consulta trayendo solo lo necesario
    lecturas_mes = LecturaEstacion.objects.filter(
        estacion=estacion,
        captura__timestamp__gte=hace_un_mes
    ).select_related('captura').only('captura__timestamp', 'bicis_disponibles')

    # Inicializamos la matriz 7 (días) x 24 (horas)
    # Estructura de celda: {'suma': 0, 'conteo': 0}
    heatmap_raw = [[{'s': 0, 'c': 0} for _ in range(24)] for _ in range(7)]

    for l in lecturas_mes:
        # Convertimos a hora local para que el patrón coincida con la realidad de Zaragoza
        fecha_local = timezone.localtime(l.captura.timestamp)
        
        dia = fecha_local.weekday() # 0=Lunes ... 6=Domingo
        hora = fecha_local.hour
        
        heatmap_raw[dia][hora]['s'] += l.bicis_disponibles
        heatmap_raw[dia][hora]['c'] += 1

    # Preparamos los datos finales para la plantilla
    dias_nombres = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom']
    heatmap_data = []

    for i in range(7):
        fila_horas = []
        for h in range(24):
            datos = heatmap_raw[i][h]
            if datos['c'] > 0:
                promedio = round(datos['s'] / datos['c'], 1)
            else:
                promedio = None # Sin datos
            fila_horas.append(promedio)
            
        heatmap_data.append({
            'nombre': dias_nombres[i],
            'horas': fila_horas
        })

    context = {
        'estacion': estacion,
        'lecturas': reversed(lecturas[-10:]), # Para la tabla (orden inverso)
        'dataset_bicis': dataset_bicis,
        'dataset_anclajes': dataset_anclajes,
        'stats': stats, # Pasamos las estadísticas
        'heatmap_data': heatmap_data, # mAPA DE CALOR
    }
    return render(request, 'core/detalle_estacion.html', context)


def mapa_estaciones(request):
    # 1. Traemos las últimas 50 capturas (aprox 4 horas) para no saturar el navegador al principio.
    # Si quieres 24h, pon [:288] (12 capturas/hora * 24).
    capturas = Captura.objects.order_by('-timestamp')[:50]
    
    # Las reordenamos cronológicamente (antiguo -> nuevo) para la animación
    capturas = reversed(capturas)
    
    timeline_data = []
    
    for c in capturas:
        # Para cada instante de tiempo, sacamos la foto de las estaciones
        fecha_local = timezone.localtime(c.timestamp)

        estado_estaciones = []
        qs = c.lecturas.select_related('estacion').all()
        
        for l in qs:
            estado_estaciones.append({
                'id': l.estacion.id_externo,
                'lat': float(l.estacion.latitud),
                'lon': float(l.estacion.longitud),
                'nombre': l.estacion.nombre,
                'bicis': l.bicis_disponibles,
                # Enviamos solo lo necesario para ahorrar datos
            })
            
        timeline_data.append({
            'timestamp': c.timestamp.isoformat(),     # Fecha ISO para código
            'hora_legible': fecha_local.strftime("%H:%M"), # Hora para mostrar al usuario
            'datos': estado_estaciones
        })

    context = {
        'timeline_json': json.dumps(list(timeline_data), cls=DjangoJSONEncoder)
    }
    return render(request, 'core/mapa_estaciones.html', context)