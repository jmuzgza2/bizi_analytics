from django.contrib import admin

# Register your models here.
from .models import Estacion, Captura, LecturaEstacion

admin.site.register(Estacion)
admin.site.register(Captura)
admin.site.register(LecturaEstacion)
