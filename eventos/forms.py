# eventos/forms.py
from django import forms

from animals.models import Animal
from .models import EventoSanitario

_TEXTO = {"class": "form-control"}
_SELECT = {"class": "form-select"}
_FECHA = {"class": "form-control", "type": "date"}


class EventoSanitarioForm(forms.ModelForm):
    """Formulario para registrar un nuevo evento sanitario (CU-003).
    Filtra animales en estado ACTIVO o BORRADOR; excluye INACTIVO.
    """

    class Meta:
        model = EventoSanitario
        fields = [
            "animal",
            "tipo",
            "fecha",
            "responsable",
            "producto",
            "dosis",
            "lote",
            "via_aplicacion",
            "notas",
        ]
        widgets = {
            "animal": forms.Select(attrs=_SELECT),
            "tipo": forms.TextInput(attrs={**_TEXTO, "placeholder": "Ej: Vacuna Aftosa"}),
            "fecha": forms.DateInput(attrs=_FECHA),
            "responsable": forms.TextInput(attrs=_TEXTO),
            "producto": forms.TextInput(attrs={**_TEXTO, "placeholder": "Nombre del producto veterinario"}),
            "dosis": forms.TextInput(attrs={**_TEXTO, "placeholder": "Ej: 2ml"}),
            "lote": forms.TextInput(attrs=_TEXTO),
            "via_aplicacion": forms.TextInput(attrs={**_TEXTO, "placeholder": "Ej: Subcutánea"}),
            "notas": forms.Textarea(attrs={**_TEXTO, "rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["animal"].queryset = Animal.objects.exclude(
            estado=Animal.Estado.INACTIVO
        ).order_by("rfid", "arete")
        self.fields["animal"].empty_label = "Seleccione un animal"
        self.fields["fecha"].initial = None  # browser renderiza la fecha del campo default


class CorreccionEventoForm(forms.ModelForm):
    """Formulario para registrar una corrección sobre un evento CONFIRMADO.
    No incluye animal ni estado (se heredan del evento original).
    """

    class Meta:
        model = EventoSanitario
        fields = [
            "tipo",
            "fecha",
            "responsable",
            "producto",
            "dosis",
            "lote",
            "via_aplicacion",
            "notas",
        ]
        widgets = {
            "tipo": forms.TextInput(attrs={**_TEXTO, "placeholder": "Ej: Vacuna Aftosa"}),
            "fecha": forms.DateInput(attrs=_FECHA),
            "responsable": forms.TextInput(attrs=_TEXTO),
            "producto": forms.TextInput(attrs={**_TEXTO, "placeholder": "Nombre del producto veterinario"}),
            "dosis": forms.TextInput(attrs={**_TEXTO, "placeholder": "Ej: 2ml"}),
            "lote": forms.TextInput(attrs=_TEXTO),
            "via_aplicacion": forms.TextInput(attrs={**_TEXTO, "placeholder": "Ej: Subcutánea"}),
            "notas": forms.Textarea(attrs={**_TEXTO, "rows": 3}),
        }
