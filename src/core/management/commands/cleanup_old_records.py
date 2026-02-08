from django.core.management.base import BaseCommand
from django.utils import timezone
from core.models import Captura
from datetime import timedelta
import time

class Command(BaseCommand):
    help = 'Elimina registros de Captura (y sus LecturaEstacion asociadas) anteriores a 30 días para liberar espacio.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Simula la ejecución mostrando cuántos registros se borrarían sin eliminarlos.',
        )
        parser.add_argument(
            '--days',
            type=int,
            default=30,
            help='Número de días de antigüedad a conservar (por defecto 30).',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Ejecuta el borrado sin pedir confirmación.',
        )
        parser.add_argument(
            '--batch-size',
            type=int,
            default=100,
            help='Cantidad de registros a borrar en cada transacción (por defecto 100).',
        )

    def handle(self, *args, **options):
        days = options['days']
        dry_run = options['dry_run']
        force = options['force']
        batch_size = options['batch_size']

        # Calcular fecha límite
        cutoff_date = timezone.now() - timedelta(days=days)
        
        self.stdout.write(self.style.WARNING(f"Buscando registros anteriores a: {cutoff_date}"))

        # Queryset total para contar
        qs = Captura.objects.filter(timestamp__lt=cutoff_date)
        total_count = qs.count()

        if total_count == 0:
            self.stdout.write(self.style.SUCCESS('No hay registros antiguos para borrar.'))
            return

        self.stdout.write(f"Se encontraron un total de {total_count} registros de 'Captura' antiguos.")

        if dry_run:
            self.stdout.write(self.style.SUCCESS(f"[DRY-RUN] Se borrarían {total_count} registros (en lotes de {batch_size})."))
            return

        # Confirmación de seguridad
        if not force:
            self.stdout.write(self.style.ERROR(f"¡ADVERTENCIA! Estás a punto de eliminar PERMANENTEMENTE {total_count} capturas históricas."))
            confirm = input("¿Estás seguro de que deseas continuar? (escribe 'si' para confirmar): ")
            if confirm.lower() != 'si':
                self.stdout.write(self.style.WARNING("Operación cancelada por el usuario."))
                return

        # LOGICA DE BORRADO POR LOTES
        self.stdout.write(f"Iniciando borrado en lotes de {batch_size}...")
        deleted_so_far = 0
        
        while deleted_so_far < total_count:
            # Seleccionamos un lote de IDs
            # Importante: Usamos list() para ejecutar la query y obtener los IDs concretos
            # De lo contrario el slice sobre un delete puede dar problemas en algunos backends o no ser eficiente
            batch_ids = list(Captura.objects.filter(timestamp__lt=cutoff_date).values_list('id', flat=True)[:batch_size])
            
            if not batch_ids:
                break
                
            # Borramos ese lote concreto
            count, _ = Captura.objects.filter(id__in=batch_ids).delete()
            
            deleted_so_far += count
            remaining = total_count - deleted_so_far
            self.stdout.write(f"Borrados {count} registros. Total borrados: {deleted_so_far}/{total_count}. Restantes aprox: {max(0, remaining)}")
            
            # Pequeña pausa para dejar respirar a la BD
            time.sleep(0.5)

        self.stdout.write(self.style.SUCCESS(f"Proceso finalizado. Total eliminados: {deleted_so_far}."))
