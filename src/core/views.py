from django.shortcuts import render, get_object_or_404
from django.utils import timezone
from django.urls import reverse
from django.db.models import Sum, Avg
from django.core.serializers.json import DjangoJSONEncoder
from django.http import JsonResponse 
import json
import math
import datetime
from datetime import timedelta
from .models import Estacion, LecturaEstacion, Captura

# --- FUNCIÓN AUXILIAR: CALCULAR DISTANCIA (Haversine) ---
def haversine(lat1, lon1, lat2, lon2):
    """Devuelve distancia en metros entre dos coordenadas."""
    R = 6371000  # Radio Tierra en metros
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c

# --- VISTAS PRINCIPALES ---

def lista_estaciones(request):
    estaciones = Estacion.objects.all().order_by('id_externo')
    desde = timezone.now() - timedelta(hours=24)
    capturas_recientes = Captura.objects.filter(timestamp__gte=desde).order_by('timestamp')
    datos_globales = []
    for c in capturas_recientes:
        total = c.lecturas.aggregate(t=Sum('bicis_disponibles'))['t']
        if total is not None:
            datos_globales.append({'x': c.timestamp.isoformat(), 'y': total})
    context = {'estaciones': estaciones, 'datos_globales': json.dumps(datos_globales, cls=DjangoJSONEncoder)}
    return render(request, 'core/lista_estaciones.html', context)

def detalle_estacion(request, estacion_id):
    estacion = get_object_or_404(Estacion, id_externo=estacion_id)
    
    # 1. Rango Temporal
    rango = request.GET.get('rango', '24h')
    if rango == '7d':
        horas_atras = 168
        titulo_rango = "Últimos 7 días"
    else:
        horas_atras = 24
        titulo_rango = "Últimas 24 horas"
        rango = '24h'

    start_date = timezone.now() - timedelta(hours=horas_atras)

    # 2. Consulta
    lecturas_query = LecturaEstacion.objects.filter(
        estacion=estacion,
        captura__timestamp__gte=start_date
    ).select_related('captura').order_by('captura__timestamp')
    
    lecturas = list(lecturas_query)
    
    # 3. Procesamiento
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

    # 4. Estadísticas
    stats = {'media_bicis': 0, 'media_anclajes': 0, 'pct_sin_bicis': 0, 'pct_sin_anclajes': 0}
    if total > 0:
        stats['media_bicis'] = round(suma_bicis / total, 1)
        stats['media_anclajes'] = round(suma_anclajes / total, 1)
        stats['pct_sin_bicis'] = round((conteo_sin_bicis / total) * 100, 1)
        stats['pct_sin_anclajes'] = round((conteo_sin_anclajes / total) * 100, 1)

    # 5. Mapa de Calor (15 min)
    hace_un_mes = timezone.now() - timedelta(days=30)
    lecturas_mes = LecturaEstacion.objects.filter(
        estacion=estacion, captura__timestamp__gte=hace_un_mes
    ).select_related('captura').only('captura__timestamp', 'bicis_disponibles')
    
    heatmap_raw = [[[{'s': 0, 'c': 0} for _ in range(4)] for _ in range(24)] for _ in range(7)]
    for l in lecturas_mes:
        fl = timezone.localtime(l.captura.timestamp)
        cuarto = fl.minute // 15
        heatmap_raw[fl.weekday()][fl.hour][cuarto]['s'] += l.bicis_disponibles
        heatmap_raw[fl.weekday()][fl.hour][cuarto]['c'] += 1

    dias_nombres = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom']
    heatmap_data = []
    for i in range(7):
        fila = []
        for h in range(24):
            bloque = []
            for q in range(4):
                d = heatmap_raw[i][h][q]
                bloque.append(round(d['s']/d['c'], 1) if d['c'] > 0 else None)
            fila.append(bloque)
        heatmap_data.append({'nombre': dias_nombres[i], 'horas': fila})

    context = {
        'estacion': estacion,
        'lecturas': list(reversed(lecturas[-10:])), 
        'dataset_bicis': dataset_bicis,
        'dataset_anclajes': dataset_anclajes,
        'stats': stats,
        'heatmap_data': heatmap_data,
        'rango_actual': rango,
        'titulo_rango': titulo_rango
    }
    return render(request, 'core/detalle_estacion.html', context)

def mapa_estaciones(request):
    hace_24h = timezone.now() - timedelta(hours=24)
    estaciones_static = {e.id_externo: {'lat': float(e.latitud), 'lon': float(e.longitud), 'nombre': e.nombre, 'url': reverse('detalle_estacion', args=[e.id_externo])} for e in Estacion.objects.all()}
    capturas = list(Captura.objects.filter(timestamp__gte=hace_24h).order_by('timestamp'))[::2]
    timeline_data = []
    for c in capturas:
        lecturas_dict = {str(item[0]): [item[1], item[2]] for item in c.lecturas.values_list('estacion__id_externo', 'bicis_disponibles', 'anclajes_libres')}
        timeline_data.append({'ts': timezone.localtime(c.timestamp).strftime("%H:%M"), 'd': lecturas_dict})
    context = {'estaciones_static': json.dumps(estaciones_static, cls=DjangoJSONEncoder), 'timeline_json': json.dumps(timeline_data, cls=DjangoJSONEncoder)}
    return render(request, 'core/mapa_estaciones.html', context)

# --- PLANIFICADOR / ORÁCULO INTELIGENTE ---

def obtener_nivel_probabilidad(porcentaje):
    """Convierte un % numérico en una escala cualitativa y estilos."""
    if porcentaje >= 80:
        return {'texto': 'Muy Alta', 'clase': 'success', 'color': '#198754', 'ancho': 100} 
    elif porcentaje >= 60:
        return {'texto': 'Alta', 'clase': 'success', 'color': '#75b798', 'ancho': 75}    
    elif porcentaje >= 40:
        return {'texto': 'Media', 'clase': 'warning', 'color': '#ffc107', 'ancho': 50}   
    elif porcentaje >= 20:
        return {'texto': 'Baja', 'clase': 'danger', 'color': '#fd7e14', 'ancho': 25}     
    else:
        return {'texto': 'Muy Baja', 'clase': 'danger', 'color': '#dc3545', 'ancho': 10} 

def calcular_prediccion_precisa(estacion_id, dia, hora, minuto):
    dummy = datetime.datetime(2000, 1, 1, hora, minuto)
    start = (dummy - timedelta(minutes=4)).time()
    end = (dummy + timedelta(minutes=4)).time()
    
    qs = LecturaEstacion.objects.filter(
        estacion__id_externo=estacion_id, 
        captura__timestamp__gte=timezone.now()-timedelta(days=60), 
        captura__timestamp__week_day=dia, 
        captura__timestamp__time__range=(start, end)
    )
    
    if not qs.exists(): return None
    
    stats = qs.aggregate(mb=Avg('bicis_disponibles'), ma=Avg('anclajes_libres'))
    mb, ma = round(stats['mb'] or 0, 1), round(stats['ma'] or 0, 1)
    
    antes = qs.filter(captura__timestamp__time__lt=dummy.time()).aggregate(m=Avg('bicis_disponibles'))['m'] or mb
    despues = qs.filter(captura__timestamp__time__gt=dummy.time()).aggregate(m=Avg('bicis_disponibles'))['m'] or mb
    diff = despues - antes
    
    tendencia = "Subiendo 📈" if diff > 0.3 else "Bajando 📉" if diff < -0.3 else "Estable 😐"
    
    pct_bici = min(100, int((mb/5.0)*100))
    pct_hueco = min(100, int((ma/5.0)*100))

    return {
        'pct_bici_num': pct_bici,
        'pct_hueco_num': pct_hueco,
        'nivel_bici': obtener_nivel_probabilidad(pct_bici),
        'nivel_hueco': obtener_nivel_probabilidad(pct_hueco),
        'media_bicis': mb, 
        'media_anclajes': ma, 
        'tendencia': tendencia
    }

def buscar_alternativas(target_estacion_id, dia, hora, minuto, tipo_busqueda):
    """Busca estaciones cercanas (max 500m) que tengan MEJOR probabilidad."""
    try:
        origen = Estacion.objects.get(id_externo=target_estacion_id)
        todas = Estacion.objects.exclude(id_externo=target_estacion_id)
        candidatas = []

        for est in todas:
            dist = haversine(float(origen.latitud), float(origen.longitud), float(est.latitud), float(est.longitud))
            if dist <= 500: 
                pred = calcular_prediccion_precisa(est.id_externo, dia, hora, minuto)
                if not pred: continue
                
                prob = pred['pct_bici_num'] if tipo_busqueda == 'bici' else pred['pct_hueco_num']
                if prob >= 60:
                    candidatas.append({
                        'nombre': est.nombre,
                        'distancia': int(dist),
                        'tiempo_pie': int(dist / 80),
                        'nivel': pred['nivel_bici'] if tipo_busqueda == 'bici' else pred['nivel_hueco'],
                        'media': pred['media_bicis'] if tipo_busqueda == 'bici' else pred['media_anclajes']
                    })

        candidatas.sort(key=lambda x: x['distancia']) 
        return candidatas[:2] 
    except:
        return []

def planificador(request):
    estaciones = Estacion.objects.all().order_by('nombre')
    res = None
    
    if 'origen' in request.GET and 'destino' in request.GET:
        try:
            o_id, d_id = request.GET.get('origen'), request.GET.get('destino')
            dia = int(request.GET.get('dia'))
            hora = int(request.GET.get('hora'))
            minuto = int(request.GET.get('minuto', 0))
            
            obj_o, obj_d = Estacion.objects.get(id_externo=o_id), Estacion.objects.get(id_externo=d_id)
            
            # 1. CÁLCULO DE VIAJE
            dist_metros = haversine(float(obj_o.latitud), float(obj_o.longitud), float(obj_d.latitud), float(obj_d.longitud))
            dist_real = dist_metros * 1.4 
            mins_viaje = max(5, int(dist_real / 200)) 
            
            # 2. LLEGADA
            llegada = datetime.datetime(2024,1,1,hora,minuto) + timedelta(minutes=mins_viaje)
            dia_llegada = dia + 1 if llegada.day != 1 else dia
            if dia_llegada > 7: dia_llegada = 1

            # 3. PREDICCIONES (HISTÓRICO)
            do = calcular_prediccion_precisa(o_id, dia, hora, minuto)
            dd = calcular_prediccion_precisa(d_id, dia_llegada, llegada.hour, llegada.minute)
            
            # --- NUEVO: DATOS REALES (AHORA MISMO) ---
            # Buscamos la última lectura real para mostrar el estado actual
            ult_captura = Captura.objects.order_by('-timestamp').last()
            lectura_o = None
            lectura_d = None
            
            if ult_captura:
                lectura_o = LecturaEstacion.objects.filter(captura=ult_captura, estacion=obj_o).first()
                lectura_d = LecturaEstacion.objects.filter(captura=ult_captura, estacion=obj_d).first()

            # Extraemos valores reales o guiones si no hay datos
            real_o_bicis = lectura_o.bicis_disponibles if lectura_o else '-'
            real_o_anclajes = lectura_o.anclajes_libres if lectura_o else '-'
            
            real_d_bicis = lectura_d.bicis_disponibles if lectura_d else '-'
            real_d_anclajes = lectura_d.anclajes_libres if lectura_d else '-'
            
            # 4. SUGERENCIAS
            sugerencias_origen = []
            sugerencias_destino = []
            if do and do['pct_bici_num'] < 40:
                sugerencias_origen = buscar_alternativas(o_id, dia, hora, minuto, 'bici')
            if dd and dd['pct_hueco_num'] < 40:
                sugerencias_destino = buscar_alternativas(d_id, dia_llegada, llegada.hour, llegada.minute, 'hueco')

            if not do: do = {'nivel_bici': {'texto': 'Sin datos', 'clase': 'secondary', 'color': '#ccc', 'ancho': 0}, 'media_bicis': 0, 'tendencia': '-'}
            if not dd: dd = {'nivel_hueco': {'texto': 'Sin datos', 'clase': 'secondary', 'color': '#ccc', 'ancho': 0}, 'media_anclajes': 0, 'tendencia': '-'}

            res = {
                'viaje': {
                    'minutos': mins_viaje, 
                    'distancia_km': round(dist_real / 1000, 1),
                    'hora_salida': f"{hora:02}:{minuto:02}", 
                    'hora_llegada': f"{llegada.hour:02}:{llegada.minute:02}",
                    'cambio_dia': (dia_llegada != dia)
                },
                'origen': {
                    'nombre': obj_o.nombre, 
                    'nivel': do['nivel_bici'],
                    'media': do['media_bicis'], 
                    'tendencia': do['tendencia'],
                    'alternativas': sugerencias_origen,
                    # Datos Reales
                    'actual_bicis': real_o_bicis,
                    'actual_anclajes': real_o_anclajes
                },
                'destino': {
                    'nombre': obj_d.nombre, 
                    'nivel': dd['nivel_hueco'], 
                    'media': dd['media_anclajes'], 
                    'tendencia': dd['tendencia'],
                    'alternativas': sugerencias_destino,
                    # Datos Reales
                    'actual_bicis': real_d_bicis,
                    'actual_anclajes': real_d_anclajes
                }
            }
        except Exception as e:
            print(f"Error planificador: {e}")
            pass
            
    return render(request, 'core/planificador.html', {'estaciones': estaciones, 'resultado': res, 'form_data': request.GET})

# --- RADAR ---
def radar_index(request): return render(request, 'core/radar.html')

def radar_carga(request):
    try: lat, lon = float(request.GET.get('lat')), float(request.GET.get('lon'))
    except: return JsonResponse({'error': 'Coords'}, status=400)
    candidatas = sorted([(haversine(lat, lon, float(e.latitud), float(e.longitud)), e) for e in Estacion.objects.all()], key=lambda x: x[0])[:3]
    res, ult = [], Captura.objects.order_by('-timestamp').last()
    if ult:
        for dist, est in candidatas:
            act = LecturaEstacion.objects.filter(captura=ult, estacion=est).first()
            if act: res.append({'id': est.id_externo, 'nombre': est.nombre, 'distancia': int(dist), 'tiempo_pie': int(dist/80), 'bicis': act.bicis_disponibles, 'anclajes': act.anclajes_libres, 'url': reverse('detalle_estacion', args=[est.id_externo])})
    return JsonResponse({'estaciones': res})