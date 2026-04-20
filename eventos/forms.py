# eventos/forms.py
from django import forms

from animals.models import Animal
from potreros.models import Potrero
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


class EventoMasivoForm(forms.Form):
    """CU-003 pasos 13-14: Registro masivo de eventos sanitarios.

    El operador elige animales (con filtro por potrero) y completa
    los datos del evento; el sistema crea un EventoSanitario por animal.
    """

    animales = forms.ModelMultipleChoiceField(
        queryset=Animal.objects.none(),  # se sobreescribe en __init__ / vista
        required=True,
        label="Animales a tratar",
        error_messages={"required": "Debe seleccionar al menos un animal."},
        widget=forms.CheckboxSelectMultiple(),
    )
    tipo = forms.CharField(
        label="Tipo de evento",
        widget=forms.TextInput(attrs={**_TEXTO, "placeholder": "Ej: Vacuna Aftosa, Desparasitación"}),
    )
    fecha = forms.DateField(
        label="Fecha",
        widget=forms.DateInput(attrs={**_FECHA}),
    )
    responsable = forms.CharField(
        label="Responsable",
        widget=forms.TextInput(attrs=_TEXTO),
    )
    producto = forms.CharField(
        label="Producto aplicado",
        widget=forms.TextInput(attrs={**_TEXTO, "placeholder": "Nombre comercial o genérico"}),
    )
    dosis = forms.CharField(
        required=False,
        label="Dosis",
        widget=forms.TextInput(attrs={**_TEXTO, "placeholder": "Ej: 2ml"}),
    )
    lote = forms.CharField(
        required=False,
        label="Lote del producto",
        widget=forms.TextInput(attrs=_TEXTO),
    )
    via_aplicacion = forms.CharField(
        required=False,
        label="Vía de aplicación",
        widget=forms.TextInput(attrs={**_TEXTO, "placeholder": "Ej: Subcutánea"}),
    )
    notas = forms.CharField(
        required=False,
        label="Observaciones",
        widget=forms.Textarea(attrs={**_TEXTO, "rows": 3}),
    )

    def __init__(self, *args, potrero=None, **kwargs):
        super().__init__(*args, **kwargs)
        qs = Animal.objects.exclude(estado=Animal.Estado.INACTIVO).order_by("rfid", "arete")
        if potrero is not None:
            qs = qs.filter(potrero=potrero)
        self.fields["animales"].queryset = qs


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
