import requests
from django.core.management.base import BaseCommand
from core.models import Estacion

class Command(BaseCommand):
    help = 'Actualiza manualmente la capacidad total y nombres de todas las estaciones existentes'

    def handle(self, *args, **kwargs):
        url_bizi = "https://www.zaragoza.es/sede/servicio/urbanismo-infraestructuras/estacion-bicicleta.json?rows=300"
        headers = {'User-Agent': 'BiziUpdater/1.0'}
        
        self.stdout.write("Conectando con API Zaragoza para actualizar metadatos...")
        
        try:
            r = requests.get(url_bizi, headers=headers)
            r.raise_for_status()
            items = r.json().get('result', [])
            
            count = 0
            for item in items:
                eid = item.get('id')
                
                # Solo nos interesa si la estación ya existe en nuestra BD
                try:
                    estacion = Estacion.objects.get(id_externo=eid)
                    
                    # Recalculamos capacidad
                    bicis = int(item.get('bicisDisponibles', 0))
                    anclajes = int(item.get('anclajesDisponibles', 0))
                    nueva_capacidad = bicis + anclajes
                    
                    # Detectamos cambios para informar
                    cambios = []
                    if estacion.capacidad_total != nueva_capacidad:
                        cambios.append(f"Cap: {estacion.capacidad_total}->{nueva_capacidad}")
                        estacion.capacidad_total = nueva_capacidad
                    
                    if estacion.nombre != item.get('title'):
                        estacion.nombre = item.get('title')
                        cambios.append("Nombre actualizado")
                    
                    # Solo guardamos si hubo cambios (Ahorro DB)
                    if cambios:
                        estacion.save()
                        self.stdout.write(f"Estación {eid} actualizada: {', '.join(cambios)}")
                        count += 1
                        
                except Estacion.DoesNotExist:
                    pass # Si hay una estación nueva, ya la creará el script de importación normal

            self.stdout.write(self.style.SUCCESS(f"¡Hecho! Se han actualizado los datos maestros de {count} estaciones."))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error: {e}"))