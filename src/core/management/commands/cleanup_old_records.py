from django.core.management.base import BaseCommand
from django.utils import timezone
from core.models import Captura
from datetime import timedelta
import sys

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

    def handle(self, *args, **options):
        days = options['days']
        dry_run = options['dry_run']
        force = options['force']

        # Calcular fecha límite
        cutoff_date = timezone.now() - timedelta(days=days)
        
        self.stdout.write(self.style.WARNING(f"Buscando registros anteriores a: {cutoff_date}"))

        # Queryset de registros a borrar
        capturas_to_delete = Captura.objects.filter(timestamp__lt=cutoff_date)
        count = capturas_to_delete.count()

        if count == 0:
            self.stdout.write(self.style.SUCCESS('No hay registros antiguos para borrar.'))
            return

        self.stdout.write(f"Se encontraron {count} registros de 'Captura' antiguos (y sus lecturas asociadas).")

        if dry_run:
            self.stdout.write(self.style.SUCCESS(f"[DRY-RUN] Se borrarían {count} registros. No se ha realizado ninguna acción."))
            return

        # Confirmación de seguridad
        if not force:
            self.stdout.write(self.style.ERROR(f"¡ADVERTENCIA! Estás a punto de eliminar PERMANENTEMENTE {count} capturas históricas."))
            confirm = input("¿Estás seguro de que deseas continuar? (escribe 'si' para confirmar): ")
            if confirm.lower() != 'si':
                self.stdout.write(self.style.WARNING("Operación cancelada por el usuario."))
                return

        # Ejecutar borrado
        deleted_count, deleted_details = capturas_to_delete.delete()
        
        self.stdout.write(self.style.SUCCESS(f"Eliminados {deleted_count} objetos en total."))
        self.stdout.write(str(deleted_details))
