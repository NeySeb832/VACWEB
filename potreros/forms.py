# potreros/forms.py
"""Formulario para crear y editar Potreros (CU-005)."""

from django import forms
from django.core.exceptions import ValidationError

from .models import Potrero


class PotreroForm(forms.ModelForm):
    """Formulario de creación/edición de Potrero.

    El campo `estado` no se expone: se gestiona desde las vistas.
    """

    class Meta:
        model = Potrero
        fields = ["nombre_codigo", "area_ha", "capacidad_maxima", "tipo_uso", "observaciones"]
        widgets = {
            "nombre_codigo": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Ej. Potrero Norte, L-01...",
                }
            ),
            "area_ha": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Ej. 12.50",
                    "step": "0.01",
                    "min": "0.01",
                }
            ),
            "capacidad_maxima": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Ej. 50",
                    "min": "1",
                }
            ),
            "tipo_uso": forms.Select(
                attrs={"class": "form-select"}
            ),
            "observaciones": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": "Observaciones opcionales...",
                }
            ),
        }
        labels = {
            "nombre_codigo":   "Nombre del Lote/Potrero",
            "area_ha":         "Área (ha)",
            "capacidad_maxima": "Capacidad máxima (animales)",
            "tipo_uso":        "Tipo de uso",
            "observaciones":   "Observaciones",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["observaciones"].required = False

    def clean_nombre_codigo(self):
        nombre = self.cleaned_data.get("nombre_codigo", "").strip()
        qs = Potrero.objects.filter(nombre_codigo__iexact=nombre)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError("Ya existe un potrero con este nombre o código.")
        return nombre

    def clean_area_ha(self):
        area = self.cleaned_data.get("area_ha")
        if area is not None and area <= 0:
            raise ValidationError("El valor debe ser mayor a cero.")
        return area

    def clean_capacidad_maxima(self):
        cap = self.cleaned_data.get("capacidad_maxima")
        if cap is not None and cap <= 0:
            raise ValidationError("El valor debe ser mayor a cero.")
        return cap
