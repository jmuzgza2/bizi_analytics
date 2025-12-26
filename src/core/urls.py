from django.urls import path
from . import views

urlpatterns = [
    # Ruta portada: Lista de todas las estaciones
    path('', views.lista_estaciones, name='lista_estaciones'),
    
    # Ruta detalle: /estacion/1/
    path('estacion/<int:estacion_id>/', views.detalle_estacion, name='detalle_estacion'),
    path('mapa/', views.mapa_estaciones, name='mapa_estaciones'),
]