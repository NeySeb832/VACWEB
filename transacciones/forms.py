# transacciones/forms.py
from datetime import date as _date
from decimal import Decimal

from django import forms

from animals.models import Animal
from .models import Transaccion

_TEXTO  = {"class": "form-control"}
_SELECT = {"class": "form-select"}
_FECHA  = {"class": "form-control", "type": "date"}


class TransaccionForm(forms.ModelForm):
    """Formulario para registrar una nueva transacción (CU-006).
    Excluye animales INACTIVO del selector.
    """

    class Meta:
        model  = Transaccion
        fields = ["tipo", "fecha", "animal", "peso_final_kg",
                  "origen_destino", "valor_cop", "observaciones"]
        widgets = {
            "tipo": forms.Select(attrs=_SELECT),
            "fecha": forms.DateInput(attrs={**_FECHA, "max": str(_date.today())}),
            "animal": forms.Select(attrs=_SELECT),
            "peso_final_kg": forms.NumberInput(
                attrs={**_TEXTO, "step": "0.01", "min": "0.01",
                       "placeholder": "Ej: 320.5 (opcional)"}
            ),
            "origen_destino": forms.TextInput(
                attrs={**_TEXTO, "placeholder": "Ej: Frigorífico Central / Finca El Roble",
                       "id": "id_origen_destino"}
            ),
            "valor_cop": forms.NumberInput(
                attrs={**_TEXTO, "step": "0.01", "min": "0.01",
                       "placeholder": "Ej: 1500000.00"}
            ),
            "observaciones": forms.Textarea(
                attrs={**_TEXTO, "rows": 3,
                       "placeholder": "Observaciones adicionales (opcional)"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["animal"].queryset = (
            Animal.objects.exclude(estado=Animal.Estado.INACTIVO)
            .order_by("rfid", "nombre")
        )
        self.fields["animal"].empty_label = "Seleccione un animal"
        self.fields["tipo"].empty_label   = "Seleccione el tipo"
        self.fields["fecha"].widget.attrs["max"] = str(_date.today())

    def clean_valor_cop(self):
        valor = self.cleaned_data.get("valor_cop")
        if valor is not None and valor <= 0:
            raise forms.ValidationError("El valor debe ser mayor a cero.")
        return valor

    def clean_fecha(self):
        fecha = self.cleaned_data.get("fecha")
        if fecha and fecha > _date.today():
            raise forms.ValidationError("La fecha no puede ser posterior a hoy.")
        return fecha

    def clean(self):
        cleaned_data = super().clean()
        tipo   = cleaned_data.get("tipo")
        animal = cleaned_data.get("animal")

        if tipo and animal:
            if tipo in (Transaccion.Tipo.VENTA, Transaccion.Tipo.SACRIFICIO):
                if animal.estado != Animal.Estado.ACTIVO:
                    self.add_error(
                        "animal",
                        f"Solo se pueden registrar ventas o sacrificios sobre animales "
                        f"en estado Activo. Estado actual: {animal.get_estado_display()}."
                    )
            elif tipo == Transaccion.Tipo.COMPRA:
                if animal.estado == Animal.Estado.INACTIVO:
                    self.add_error(
                        "animal",
                        "No se puede registrar una compra sobre un animal en estado Inactivo."
                    )
        return cleaned_data


class AnimalInlineForm(forms.Form):
    """CU-006: Crear un animal nuevo en el flujo de una COMPRA.

    Todos los campos son opcionales en el formulario —
    la vista valida que RFID o Nombre esté presente cuando crear_animal=True.
    """
    crear_animal = forms.BooleanField(
        required=False,
        label="Crear animal nuevo en esta compra",
        widget=forms.CheckboxInput(attrs={"class": "form-check-input", "id": "id_crear_animal"}),
    )
    ani_rfid = forms.CharField(
        required=False, max_length=32,
        label="RFID del animal",
        widget=forms.TextInput(attrs={**_TEXTO, "placeholder": "RFID (chapeta) — opcional si hay nombre"}),
    )
    ani_nombre = forms.CharField(
        required=False, max_length=32,
        label="Nombre del animal",
        widget=forms.TextInput(attrs={**_TEXTO, "placeholder": "Nombre del animal (ej: La Negra)"}),
    )
    ani_sexo = forms.ChoiceField(
        required=False,
        label="Sexo",
        choices=[("", "Seleccione"), ("M", "Macho"), ("F", "Hembra")],
        widget=forms.Select(attrs=_SELECT),
    )
    ani_etapa = forms.ChoiceField(
        required=False,
        label="Etapa productiva",
        choices=[("", "Seleccione"), ("TER", "Ternero"), ("DES", "Destete"),
                 ("LEV", "Levante/Ceba"), ("NOV", "Novillo"), ("ADU", "Adulto")],
        widget=forms.Select(attrs=_SELECT),
    )
    ani_raza = forms.CharField(
        required=False, max_length=48,
        label="Raza",
        widget=forms.TextInput(attrs={**_TEXTO, "placeholder": "Ej: Brahman"}),
    )
    ani_procedencia = forms.CharField(
        required=False, max_length=120,
        label="Procedencia",
        widget=forms.TextInput(attrs={**_TEXTO, "placeholder": "Finca o proveedor de origen"}),
    )
    ani_peso_entrada = forms.DecimalField(
        required=False, max_digits=7, decimal_places=2, min_value=Decimal("0.01"),
        label="Peso de entrada (kg)",
        widget=forms.NumberInput(attrs={**_TEXTO, "step": "0.01", "placeholder": "Ej: 250.5"}),
    )

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("crear_animal"):
            rfid   = cleaned.get("ani_rfid",   "").strip()
            nombre = cleaned.get("ani_nombre", "").strip()
            if not rfid and not nombre:
                raise forms.ValidationError(
                    "Para crear un animal debes indicar al menos el RFID o el Nombre."
                )
        return cleaned


class AnulacionTransaccionForm(forms.Form):
    motivo = forms.CharField(
        label="Motivo de anulación",
        min_length=10,
        widget=forms.Textarea(
            attrs={"class": "form-control", "rows": 4,
                   "placeholder": "Describa el motivo de la anulación (mínimo 10 caracteres)..."}
        ),
    )

    def clean_motivo(self):
        motivo = self.cleaned_data.get("motivo", "").strip()
        if not motivo:
            raise forms.ValidationError("El motivo de anulación no puede estar vacío.")
        return motivo
