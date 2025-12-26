import time
import schedule
from django.core.management.base import BaseCommand
from django.core.management import call_command
from django.utils import timezone

class Command(BaseCommand):
    help = 'Monitor inteligente: Frecuencia variable según hora del día'

    def tarea_inteligente(self):
        """
        Se ejecuta cada minuto para evaluar si toca cargar datos.
        - Noche (00:00 - 06:00): Cada 15 min.
        - Día (06:00 - 23:59): Cada 3 min.
        """
        # Obtenemos la hora actual CON zona horaria (Europe/Madrid)
        ahora = timezone.localtime()
        hora = ahora.hour
        minuto = ahora.minute

        # 1. Definimos el intervalo según la hora
        if 0 <= hora < 6:
            intervalo = 15
            modo = "NOCHE 🌙"
        else:
            intervalo = 3
            modo = "DÍA ☀️"

        # 2. Comprobamos si el minuto actual es múltiplo del intervalo
        # Ejemplo: Si intervalo es 3, ejecuta en minutos 0, 3, 6, 9...
        if minuto % intervalo == 0:
            self.stdout.write(f"\n[Monitor {ahora.strftime('%H:%M')}] Modo {modo} (Cada {intervalo} min) -> EJECUTANDO")
            try:
                call_command('cargar_datos')
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Error: {e}"))
        else:
            # Opción verbose para depurar (puedes quitarlo si ensucia mucho el log)
            # self.stdout.write(f"[Monitor {ahora.strftime('%H:%M')}] Esperando... (Toca en el siguiente múltiplo de {intervalo})")
            pass

    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.SUCCESS("--- Iniciando Monitor Inteligente Bizi ---"))
        self.stdout.write("Horario: 00-06h (15 min) | 06-00h (3 min)")

        # 1. Ejecución inmediata al arrancar (para no esperar)
        self.stdout.write(">> Primera carga de arranque...")
        call_command('cargar_datos')

        # 2. Programamos el 'Chequeo' cada 1 minuto exacto.
        # El script despierta cada minuto, comprueba la regla de tiempo y decide.
        schedule.every(1).minutes.at(":00").do(self.tarea_inteligente)

        # 3. Bucle infinito
        while True:
            schedule.run_pending()
            time.sleep(1)