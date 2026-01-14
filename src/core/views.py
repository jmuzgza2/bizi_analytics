from django.shortcuts import render, get_object_or_404
from django.utils import timezone
from django.urls import reverse
from django.db.models import Sum, Avg, Count, Q, F, FloatField, ExpressionWrapper
from django.core.serializers.json import DjangoJSONEncoder
from django.http import JsonResponse 
import json
import math
import datetime
from datetime import timedelta
from .models import Estacion, LecturaEstacion, Captura

# --- FUNCIONES AUXILIARES ---

def haversine(lat1, lon1, lat2, lon2):
    """Calcula distancia en metros entre dos coordenadas"""
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c

def get_ultima_actualizacion():
    """Devuelve el timestamp de la última captura válida para el footer legal"""
    ultima = Captura.objects.filter(lecturas__isnull=False).order_by('-timestamp').first()
    return ultima.timestamp if ultima else timezone.now()

def obtener_nivel_probabilidad(porcentaje):
    if porcentaje >= 80: return {'texto': 'Muy Alta', 'clase': 'success', 'color': '#198754', 'ancho': 100}
    elif porcentaje >= 60: return {'texto': 'Alta', 'clase': 'success', 'color': '#75b798', 'ancho': 75}
    elif porcentaje >= 40: return {'texto': 'Media', 'clase': 'warning', 'color': '#ffc107', 'ancho': 50}
    elif porcentaje >= 20: return {'texto': 'Baja', 'clase': 'danger', 'color': '#fd7e14', 'ancho': 25}
    else: return {'texto': 'Muy Baja', 'clase': 'danger', 'color': '#dc3545', 'ancho': 10}

# --- VISTAS ---

def lista_estaciones(request):
    estaciones = Estacion.objects.all().order_by('id_externo')
    desde = timezone.now() - timedelta(hours=24)
    capturas_recientes = Captura.objects.filter(timestamp__gte=desde).order_by('timestamp')
    datos_globales = []
    
    # Optimización: Agregación en base de datos si fuera posible, aquí mantenemos lógica python
    for c in capturas_recientes:
        total = c.lecturas.aggregate(t=Sum('bicis_disponibles'))['t']
        if total is not None:
            datos_globales.append({'x': c.timestamp.isoformat(), 'y': total})
            
    context = {
        'estaciones': estaciones, 
        'datos_globales': json.dumps(datos_globales, cls=DjangoJSONEncoder),
        'last_update': get_ultima_actualizacion()
    }
    return render(request, 'core/lista_estaciones.html', context)

def detalle_estacion(request, estacion_id):
    estacion = get_object_or_404(Estacion, id_externo=estacion_id)
    rango = request.GET.get('rango', '24h')
    
    if rango == '7d':
        horas_atras, titulo_rango = 168, "Últimos 7 días"
    else:
        horas_atras, titulo_rango, rango = 24, "Últimas 24 horas", '24h'

    start_date = timezone.now() - timedelta(hours=horas_atras)
    # Optimización: select_related para evitar N+1 queries
    lecturas = list(LecturaEstacion.objects.filter(estacion=estacion, captura__timestamp__gte=start_date).select_related('captura').order_by('captura__timestamp'))
    
    dataset_bicis, dataset_anclajes = [], []
    s_b, s_a, c_sb, c_sa = 0, 0, 0, 0
    
    for l in lecturas:
        ts = l.captura.timestamp.isoformat()
        dataset_bicis.append({'x': ts, 'y': l.bicis_disponibles})
        dataset_anclajes.append({'x': ts, 'y': l.anclajes_libres})
        s_b += l.bicis_disponibles
        s_a += l.anclajes_libres
        if l.bicis_disponibles == 0: c_sb += 1
        if l.anclajes_libres == 0: c_sa += 1

    total = len(lecturas)
    stats = {'media_bicis': 0, 'media_anclajes': 0, 'pct_sin_bicis': 0, 'pct_sin_anclajes': 0}
    if total > 0:
        stats = {
            'media_bicis': round(s_b/total, 1), 'media_anclajes': round(s_a/total, 1),
            'pct_sin_bicis': round((c_sb/total)*100, 1), 'pct_sin_anclajes': round((c_sa/total)*100, 1)
        }

    # Heatmap
    lecturas_mes = LecturaEstacion.objects.filter(estacion=estacion, captura__timestamp__gte=timezone.now()-timedelta(days=30)).select_related('captura').only('captura__timestamp', 'bicis_disponibles')
    heatmap_raw = [[[{'s': 0, 'c': 0} for _ in range(4)] for _ in range(24)] for _ in range(7)]
    for l in lecturas_mes:
        fl = timezone.localtime(l.captura.timestamp)
        heatmap_raw[fl.weekday()][fl.hour][fl.minute//15]['s'] += l.bicis_disponibles
        heatmap_raw[fl.weekday()][fl.hour][fl.minute//15]['c'] += 1

    heatmap_data = [{'nombre': ['Lun','Mar','Mié','Jue','Vie','Sáb','Dom'][i], 'horas': [[round(heatmap_raw[i][h][q]['s']/heatmap_raw[i][h][q]['c'], 1) if heatmap_raw[i][h][q]['c']>0 else None for q in range(4)] for h in range(24)]} for i in range(7)]

    context = {
        'estacion': estacion, 
        'lecturas': list(reversed(lecturas[-10:])), 
        'dataset_bicis': dataset_bicis, 
        'dataset_anclajes': dataset_anclajes, 
        'stats': stats, 
        'heatmap_data': heatmap_data, 
        'rango_actual': rango, 
        'titulo_rango': titulo_rango,
        'last_update': get_ultima_actualizacion()
    }
    return render(request, 'core/detalle_estacion.html', context)

def mapa_estaciones(request):
    hace_24h = timezone.now() - timedelta(hours=24)
    estaciones_static = {e.id_externo: {'lat': float(e.latitud), 'lon': float(e.longitud), 'nombre': e.nombre, 'url': reverse('detalle_estacion', args=[e.id_externo])} for e in Estacion.objects.all()}
    capturas = list(Captura.objects.filter(timestamp__gte=hace_24h).order_by('timestamp'))[::2]
    timeline_data = [{'ts': timezone.localtime(c.timestamp).strftime("%H:%M"), 'd': {str(i[0]): [i[1], i[2]] for i in c.lecturas.values_list('estacion__id_externo', 'bicis_disponibles', 'anclajes_libres')}} for c in capturas]
    
    context = {
        'estaciones_static': json.dumps(estaciones_static, cls=DjangoJSONEncoder), 
        'timeline_json': json.dumps(timeline_data, cls=DjangoJSONEncoder),
        'last_update': get_ultima_actualizacion()
    }
    return render(request, 'core/mapa_estaciones.html', context)

# --- NUEVA VISTA DE ANALÍTICA (RANKING Y FILTROS) ---

def analitica_global(request):
    """
    Vista nueva para mostrar ránkings y estadísticas avanzadas.
    Permite filtrar horario nocturno.
    """
    # 1. Toggle Nocturno (00:00 - 06:00)
    ignore_night = request.GET.get('ignore_night', 'false') == 'true'
    dias_atras = 7 # Analizar última semana por defecto
    
    limite = timezone.now() - timedelta(days=dias_atras)
    queryset = LecturaEstacion.objects.filter(captura__timestamp__gte=limite)

    if ignore_night:
        # Excluir horas de 0 a 5 (00:00 a 05:59)
        queryset = queryset.exclude(captura__timestamp__hour__range=(0, 5))

    # 2. Ranking de estaciones "Offline" o "Rotas" (0 bicis y 0 anclajes)
    # Agrupamos por estación y calculamos el % de veces que reportó 0/0
    ranking = queryset.values('estacion__id_externo', 'estacion__nombre').annotate(
        total_registros=Count('id'),
        fallos=Count('id', filter=Q(bicis_disponibles=0) | Q(anclajes_libres=0))
    ).annotate(
        porcentaje_fallo=ExpressionWrapper(
            F('fallos') * 100.0 / F('total_registros'),
            output_field=FloatField()
        )
    ).exclude(total_registros=0).order_by('-porcentaje_fallo')[:15] # Top 15

    context = {
        'ranking': list(ranking),
        'ignore_night': ignore_night,
        'dias_atras': dias_atras,
        'last_update': get_ultima_actualizacion()
    }
    return render(request, 'core/analitica.html', context)

# --- ORÁCULO INTELIGENTE (PLANIFICADOR) ---

def calcular_prediccion_precisa(estacion_id, dia, hora, minuto):
    dummy = datetime.datetime(2000, 1, 1, hora, minuto)
    start, end = (dummy - timedelta(minutes=4)).time(), (dummy + timedelta(minutes=4)).time()
    qs = LecturaEstacion.objects.filter(estacion__id_externo=estacion_id, captura__timestamp__gte=timezone.now()-timedelta(days=60), captura__timestamp__week_day=dia, captura__timestamp__time__range=(start, end))
    
    if not qs.exists(): return None
    stats = qs.aggregate(mb=Avg('bicis_disponibles'), ma=Avg('anclajes_libres'))
    mb, ma = round(stats['mb'] or 0, 1), round(stats['ma'] or 0, 1)
    
    antes = qs.filter(captura__timestamp__time__lt=dummy.time()).aggregate(m=Avg('bicis_disponibles'))['m'] or mb
    despues = qs.filter(captura__timestamp__time__gt=dummy.time()).aggregate(m=Avg('bicis_disponibles'))['m'] or mb
    tendencia = "Subiendo 📈" if (despues - antes) > 0.3 else "Bajando 📉" if (despues - antes) < -0.3 else "Estable 😐"
    
    pct_bici, pct_hueco = min(100, int((mb/5.0)*100)), min(100, int((ma/5.0)*100))
    return {'pct_bici_num': pct_bici, 'pct_hueco_num': pct_hueco, 'media_bicis': mb, 'media_anclajes': ma, 'tendencia': tendencia}

def buscar_alternativas(target_id, dia, hora, minuto, tipo):
    try:
        origen = Estacion.objects.get(id_externo=target_id)
        ult_captura = Captura.objects.filter(lecturas__isnull=False).distinct().order_by('-timestamp').first()
        candidatas = []
        for est in Estacion.objects.exclude(id_externo=target_id):
            dist = haversine(float(origen.latitud), float(origen.longitud), float(est.latitud), float(est.longitud))
            if dist <= 500:
                pred = calcular_prediccion_precisa(est.id_externo, dia, hora, minuto)
                if not pred: continue
                
                dato_real = '-'
                if ult_captura:
                    lec = LecturaEstacion.objects.filter(captura=ult_captura, estacion=est).first()
                    if lec: dato_real = lec.bicis_disponibles if tipo == 'bici' else lec.anclajes_libres
                
                prob = pred['pct_bici_num'] if tipo == 'bici' else pred['pct_hueco_num']
                if prob >= 60:
                    candidatas.append({
                        'nombre': est.nombre, 'distancia': int(dist), 'tiempo_pie': int(dist/80),
                        'nivel': obtener_nivel_probabilidad(prob), 'dato_real': dato_real
                    })
        return sorted(candidatas, key=lambda x: x['distancia'])[:2]
    except: return []

def planificador(request):
    estaciones = Estacion.objects.all().order_by('nombre')
    res = None
    if 'origen' in request.GET and 'destino' in request.GET:
        try:
            o_id, d_id = request.GET.get('origen'), request.GET.get('destino')
            dia, hora, minuto = int(request.GET.get('dia')), int(request.GET.get('hora')), int(request.GET.get('minuto', 0))
            obj_o, obj_d = Estacion.objects.get(id_externo=o_id), Estacion.objects.get(id_externo=d_id)
            
            now = timezone.localtime()
            target_salida = now.replace(hour=hora, minute=minuto, second=0, microsecond=0)
            mins_diff = (target_salida - now).total_seconds() / 60
            
            dist = haversine(float(obj_o.latitud), float(obj_o.longitud), float(obj_d.latitud), float(obj_d.longitud)) * 1.4
            mins_viaje = max(5, int(dist / 200))
            llegada = target_salida + timedelta(minutes=mins_viaje)
            dia_llegada = dia + 1 if llegada.day != target_salida.day else dia
            if dia_llegada > 7: dia_llegada = 1

            ult = Captura.objects.filter(lecturas__isnull=False).distinct().order_by('-timestamp').first()
            ro, rd = {'b': 0, 'a': 0}, {'b': 0, 'a': 0}
            so_real, sd_real, hay_real = 0, 0, False
            
            if ult:
                lo = LecturaEstacion.objects.filter(captura=ult, estacion=obj_o).first()
                ld = LecturaEstacion.objects.filter(captura=ult, estacion=obj_d).first()
                if lo: 
                    ro = {'b': lo.bicis_disponibles, 'a': lo.anclajes_libres}
                    so_real = min(100, int((lo.bicis_disponibles/5.0)*100))
                    hay_real = True
                if ld:
                    rd = {'b': ld.bicis_disponibles, 'a': ld.anclajes_libres}
                    sd_real = min(100, int((ld.anclajes_libres/5.0)*100))

            do_hist = calcular_prediccion_precisa(o_id, dia, hora, minuto)
            dd_hist = calcular_prediccion_precisa(d_id, dia_llegada, llegada.hour, llegada.minute)
            so_hist = do_hist['pct_bici_num'] if do_hist else 0
            sd_hist = dd_hist['pct_hueco_num'] if dd_hist else 0

            peso_real, fuente = 0.0, "Histórico 📚"
            
            if mins_diff > -20 and mins_diff < 1440:
                if mins_diff < 20: 
                    peso_real = 1.0
                    fuente = "Tiempo Real 📡"
                elif mins_diff < 120: 
                    peso_real = 1.0 - ((mins_diff - 20)/100.0)
                    fuente = "Híbrido 🧠"
            
            if not hay_real: peso_real = 0.0

            prob_o = (so_real * peso_real) + (so_hist * (1 - peso_real))
            prob_d = (sd_real * peso_real) + (sd_hist * (1 - peso_real))

            sug_o = buscar_alternativas(o_id, dia, hora, minuto, 'bici') if prob_o < 50 else []
            sug_d = buscar_alternativas(d_id, dia_llegada, llegada.hour, llegada.minute, 'hueco') if prob_d < 50 else []

            res = {
                'viaje': {'minutos': mins_viaje, 'distancia_km': round(dist/1000, 1), 'hora_salida': f"{hora:02}:{minuto:02}", 'hora_llegada': f"{llegada.hour:02}:{llegada.minute:02}", 'fuente': fuente},
                'origen': {'nombre': obj_o.nombre, 'nivel': obtener_nivel_probabilidad(prob_o), 'actual_bicis': ro['b'], 'media': do_hist['media_bicis'] if do_hist else 0, 'tendencia': do_hist['tendencia'] if do_hist else '-', 'alternativas': sug_o},
                'destino': {'nombre': obj_d.nombre, 'nivel': obtener_nivel_probabilidad(prob_d), 'actual_anclajes': rd['a'], 'media': dd_hist['media_anclajes'] if dd_hist else 0, 'tendencia': dd_hist['tendencia'] if dd_hist else '-', 'alternativas': sug_d}
            }
        except Exception as e: print(f"Error: {e}")
    
    context = {
        'estaciones': estaciones, 
        'resultado': res, 
        'form_data': request.GET,
        'last_update': get_ultima_actualizacion()
    }
    return render(request, 'core/planificador.html', context)

def radar_index(request): 
    return render(request, 'core/radar.html', {'last_update': get_ultima_actualizacion()})

def radar_carga(request):
    try: 
        lat = float(request.GET.get('lat'))
        lon = float(request.GET.get('lon'))
    except (TypeError, ValueError): 
        return JsonResponse({'error': 'Coordenadas inválidas'}, status=400)

    candidatas = sorted([(haversine(lat, lon, float(e.latitud), float(e.longitud)), e) for e in Estacion.objects.all()], key=lambda x: x[0])[:5]
    
    ult = Captura.objects.filter(lecturas__isnull=False).distinct().order_by('-timestamp').first()
    
    res = []
    if ult:
        for dist, est in candidatas:
            act = LecturaEstacion.objects.filter(captura=ult, estacion=est).first()
            if act: 
                res.append({
                    'id': est.id_externo, 
                    'nombre': est.nombre, 
                    'distancia': int(dist), 
                    'tiempo_pie': int(dist/80), 
                    'bicis': act.bicis_disponibles, 
                    'anclajes': act.anclajes_libres,
                    'lat': float(est.latitud),
                    'lon': float(est.longitud),
                    'url': reverse('detalle_estacion', args=[est.id_externo])
                })
    
    return JsonResponse({'estaciones': res})