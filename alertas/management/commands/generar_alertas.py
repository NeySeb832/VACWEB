from django.core.management.base import BaseCommand

from alertas.models import ReglaAlerta
from alertas.services import (
    evaluar_sanitaria_proxima_vacuna,
    evaluar_sanitaria_vacuna_vencida,
    evaluar_productiva_variacion_peso,
    evaluar_productiva_sin_pesaje,
    evaluar_potrero_capacidad,
    evaluar_inventario_sin_potrero,
    evaluar_inventario_borrador,
)

EVALUADORES = [
    ("sanitaria",  "proxima_vacuna",  evaluar_sanitaria_proxima_vacuna),
    ("sanitaria",  "vacuna_vencida",  evaluar_sanitaria_vacuna_vencida),
    ("productiva", "variacion_peso",  evaluar_productiva_variacion_peso),
    ("productiva", "sin_pesaje",      evaluar_productiva_sin_pesaje),
    ("potrero",    "capacidad",       evaluar_potrero_capacidad),
    ("inventario", "sin_potrero",     evaluar_inventario_sin_potrero),
    ("inventario", "borrador",        evaluar_inventario_borrador),
]


class Command(BaseCommand):
    help = "Genera alertas automáticas evaluando todas las reglas activas."

    def handle(self, *args, **options):
        self.stdout.write("Iniciando generación de alertas...")
        reglas_activas = {
            (r.tipo, r.subtipo)
            for r in ReglaAlerta.objects.filter(activa=True)
        }
        total = 0
        for tipo, subtipo, fn in EVALUADORES:
            if (tipo, subtipo) in reglas_activas:
                n = fn()
                total += n
                self.stdout.write(f"  {tipo}/{subtipo}: {n} alerta(s) generada(s)")
            else:
                self.stdout.write(
                    self.style.WARNING(f"  Regla inactiva/inexistente: {tipo}/{subtipo}")
                )

        self.stdout.write(self.style.SUCCESS(f"Total generadas: {total}"))
        return str(total)
