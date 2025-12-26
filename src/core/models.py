from django.db import models

class Estacion(models.Model):
    # Usamos el ID oficial de Bizi como clave primaria
    id_externo = models.IntegerField(primary_key=True, help_text="ID oficial de la estación Bizi")
    nombre = models.CharField(max_length=255)
    direccion = models.CharField(max_length=255, blank=True, null=True)
    latitud = models.FloatField()
    longitud = models.FloatField()
    capacidad_total = models.IntegerField(null=True, blank=True, help_text="Suma de anclajes + bicis")
    fecha_alta = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.id_externo} - {self.nombre}"

class Captura(models.Model):
    """
    La 'foto' del momento. Guarda el contexto (Meteo + Tiempo)
    para no repetir datos en cada estación.
    """
    timestamp = models.DateTimeField(db_index=True, unique=True)
    
    # Datos para la futura IA
    temperatura = models.FloatField(help_text="Grados centígrados")
    viento_kmh = models.FloatField(help_text="Velocidad viento km/h")
    precipitacion = models.FloatField(default=0.0, help_text="Lluvia mm")
    codigo_clima = models.IntegerField(help_text="Código WMO")
    
    # Datos de Calendario
    es_festivo = models.BooleanField(default=False)
    es_fin_semana = models.BooleanField(default=False)
    
    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f"Captura {self.timestamp.strftime('%d/%m/%Y %H:%M')}"

class LecturaEstacion(models.Model):
    """
    El dato real de ocupación.
    """
    ESTADOS = [
        ('OPN', 'Operativa'),
        ('CLS', 'Cerrada'),
        ('BON', 'Solo Bicis'),
    ]

    captura = models.ForeignKey(Captura, on_delete=models.CASCADE, related_name='lecturas')
    estacion = models.ForeignKey(Estacion, on_delete=models.CASCADE, related_name='historico')
    
    bicis_disponibles = models.IntegerField()
    anclajes_libres = models.IntegerField()
    estado = models.CharField(max_length=3, choices=ESTADOS, default='OPN')

    class Meta:
        # Evita duplicados si el script se ejecuta dos veces por error
        constraints = [
            models.UniqueConstraint(fields=['captura', 'estacion'], name='unique_lectura_por_captura')
        ]