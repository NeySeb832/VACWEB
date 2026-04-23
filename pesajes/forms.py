# pesajes/forms.py
from django import forms

from animals.models import Animal
from .models import Pesaje

_TEXTO = {"class": "form-control"}
_FECHA = {"class": "form-control", "type": "date"}


class PesajeForm(forms.ModelForm):
    """Formulario para registrar un nuevo pesaje (CU-004).
    Solo muestra animales en estado ACTIVO.
    """

    class Meta:
        model = Pesaje
        fields = ["animal", "fecha", "peso_kg", "responsable", "observaciones", "foto_bascula"]
        widgets = {
            "animal": forms.Select(attrs={"class": "form-select"}),
            "fecha": forms.DateInput(attrs=_FECHA),
            "peso_kg": forms.NumberInput(
                attrs={**_TEXTO, "placeholder": "Ej: 254.5", "step": "0.01", "min": "0.01"}
            ),
            "responsable": forms.TextInput(
                attrs={**_TEXTO, "placeholder": "Nombre del operario o veterinario"}
            ),
            "observaciones": forms.Textarea(
                attrs={
                    **_TEXTO,
                    "rows": 3,
                    "placeholder": "Observaciones opcionales. Si es una corrección, referenciar el pesaje incorrecto.",
                }
            ),
            "foto_bascula": forms.ClearableFileInput(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["animal"].queryset = Animal.objects.filter(
            estado=Animal.Estado.ACTIVO
        ).order_by("rfid", "nombre")
        self.fields["animal"].empty_label = "Seleccione un animal"
