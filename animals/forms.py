# animals/forms.py
from django import forms

from .models import Animal, Potrero


class AnimalForm(forms.ModelForm):
    """
    Formulario principal para crear/editar animales (CU-002).
    Respeta las RN definidas en el modelo (clean()).
    """

    class Meta:
        model = Animal
        fields = [
            "rfid",
            "nombre",
            "sexo",
            "etapa",
            "raza",
            "fecha_nacimiento",
            "potrero",
            "estado",
            "motivo_baja",
            "foto",
            # CU-002: campos de ingreso
            "fecha_ingreso",
            "peso_entrada",
            "procedencia",
        ]
        widgets = {
            "rfid": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "RFID — identificador principal (chapeta)",
                }
            ),
            "nombre": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Nombre del animal (ej: La Negra, El Gordo)",
                }
            ),
            "sexo": forms.Select(attrs={"class": "form-select"}),
            "etapa": forms.Select(attrs={"class": "form-select"}),
            "raza": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Ej. Brahman, Normando...",
                }
            ),
            "fecha_nacimiento": forms.DateInput(
                attrs={"class": "form-control", "type": "date"}
            ),
            "potrero": forms.Select(attrs={"class": "form-select"}),
            "estado": forms.Select(attrs={"class": "form-select"}),
            "motivo_baja": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Motivo de baja lógica (si aplica)",
                }
            ),
            "foto": forms.ClearableFileInput(attrs={"class": "form-control"}),
            # CU-002 nuevos
            "fecha_ingreso": forms.DateInput(
                attrs={"class": "form-control", "type": "date"}
            ),
            "peso_entrada": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "step": "0.01",
                    "min": "0.01",
                    "placeholder": "Ej: 250.5",
                }
            ),
            "procedencia": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Ej: Finca El Roble / Proveedor X",
                }
            ),
        }
        help_texts = {
            "estado": "Si marcas ACTIVO, se validan datos mínimos (RFID/nombre, sexo, etapa y potrero).",
            "potrero": "Potrero/lote actual donde se encuentra el animal.",
            "peso_entrada": "Peso al momento del ingreso (kg). Solo informativo.",
            "procedencia": "Finca de origen, propietario anterior o proveedor.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Potreros activos por defecto (RN-4), manteniendo el actual aunque esté inactivo
        qs = Potrero.objects.filter(estado="ACTIVO")
        if self.instance.pk and self.instance.potrero_id and self.instance.potrero not in qs:
            qs = Potrero.objects.filter(pk=self.instance.potrero_id) | qs

        self.fields["potrero"].queryset = qs.order_by("nombre_codigo")
        self.fields["potrero"].empty_label = "Seleccione un potrero"

        # Etiquetas más amigables
        self.fields["rfid"].label = "RFID (identificador principal)"
        self.fields["nombre"].label = "Nombre del animal"
        self.fields["motivo_baja"].label = "Motivo de baja"
