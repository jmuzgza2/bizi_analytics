import requests
import holidays  # <--- IMPORTANTE: La librería de festivos
from django.core.management.base import BaseCommand
from django.utils import timezone
from core.models import Captura, Estacion, LecturaEstacion 

class Command(BaseCommand):
    help = 'Crea una Captura con datos de clima y festivos, y guarda el estado de las estaciones'

    def handle(self, *args, **kwargs):
        now = timezone.now()
        fecha_hoy = now.date() # Solo la fecha para comprobar festivos
        self.stdout.write(f"--- Iniciando Captura: {now} ---")

        # 1. OBTENER CLIMA (Open-Meteo)
        url_clima = "https://api.open-meteo.com/v1/forecast?latitude=41.6488&longitude=-0.8891&current=temperature_2m,wind_speed_10m,precipitation,weather_code&wind_speed_unit=kmh"
        
        try:
            r = requests.get(url_clima)
            r.raise_for_status()
            data_clima = r.json().get('current', {})
            
            temp = data_clima.get('temperature_2m', 0.0)
            viento = data_clima.get('wind_speed_10m', 0.0)
            lluvia = data_clima.get('precipitation', 0.0)
            wmo_code = data_clima.get('weather_code', 0)

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error clima: {e}. Usando valores por defecto."))
            temp, viento, lluvia, wmo_code = (0.0, 0.0, 0.0, 0)

        # 2. CALCULAR CALENDARIO (Con librería 'holidays')
        # Cargamos festivos de España (ES) y específicamente de Aragón (AR)
        # Esto incluye: Navidad, Año Nuevo, Reyes, Pilar, San Jorge, etc.
        es_festivos_aragon = holidays.ES(subdiv='AR')
        
        # Comprobamos si HOY es festivo en la lista
        es_festivo = fecha_hoy in es_festivos_aragon
        
        # Fin de semana: 5=Sábado, 6=Domingo
        es_fin_semana = now.weekday() >= 5

        # 3. CREAR LA CAPTURA (PADRE)
        try:
            captura = Captura.objects.create(
                timestamp=now,
                temperatura=temp,
                viento_kmh=viento,
                precipitacion=lluvia,
                codigo_clima=wmo_code,
                es_fin_semana=es_fin_semana,
                es_festivo=es_festivo
            )
            # Info extra para el log
            tipo_dia = "FESTIVO" if es_festivo else ("FINDE" if es_fin_semana else "LABORABLE")
            self.stdout.write(self.style.SUCCESS(f"Captura ({tipo_dia}). T: {temp}°C, V: {viento}km/h"))
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error creando Captura: {e}"))
            return

        # 4. OBTENER DATOS BIZI Y GUARDAR ESTADOS (HIJOS)
        url_bizi = "https://www.zaragoza.es/sede/servicio/urbanismo-infraestructuras/estacion-bicicleta.json?rows=300"
        headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            }

        try:
            r_bizi = requests.get(url_bizi, headers=headers)
            r_bizi.raise_for_status()
            items = r_bizi.json().get('result', [])

            estados_a_crear = []
            
            for item in items:
                eid = item.get('id')
                coords = item.get('geometry', {}).get('coordinates', [0,0])

                bicis = int(item.get('bicisDisponibles', 0))
                anclajes = int(item.get('anclajesDisponibles', 0))
                capacidad_calculada = bicis + anclajes
                
                estacion_obj, _ = Estacion.objects.get_or_create(
                    id_externo=eid,
                    defaults={
                        'nombre': item.get('title', 'Desconocido'),
                        'latitud': coords[1],
                        'longitud': coords[0],
                        'capacidad_total': capacidad_calculada
                    }
                )

                estados_a_crear.append(LecturaEstacion(
                    captura=captura,
                    estacion=estacion_obj,
                    bicis_disponibles=int(item.get('bicisDisponibles', 0)),
                    anclajes_libres=int(item.get('anclajesDisponibles', 0))  # Cambiado aquí
                ))

            LecturaEstacion.objects.bulk_create(estados_a_crear)
            self.stdout.write(self.style.SUCCESS(f"Guardados {len(estados_a_crear)} registros de estaciones."))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error Bizi: {e}"))