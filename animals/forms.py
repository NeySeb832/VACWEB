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
            "arete",
            "sexo",
            "etapa",
            "raza",
            "fecha_nacimiento",
            "potrero",
            "estado",
            "motivo_baja",
            "foto",
        ]
        widgets = {
            "rfid": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "RFID (opcional si usas arete)",
                }
            ),
            "arete": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Arete visual o alias",
                }
            ),
            "sexo": forms.Select(
                attrs={
                    "class": "form-select",
                }
            ),
            "etapa": forms.Select(
                attrs={
                    "class": "form-select",
                }
            ),
            "raza": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Ej. Brahman, Normando...",
                }
            ),
            "fecha_nacimiento": forms.DateInput(
                attrs={
                    "class": "form-control",
                    "type": "date",
                }
            ),
            "potrero": forms.Select(
                attrs={
                    "class": "form-select",
                }
            ),
            "estado": forms.Select(
                attrs={
                    "class": "form-select",
                }
            ),
            "motivo_baja": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Motivo de baja lógica (si aplica)",
                }
            ),
            "foto": forms.ClearableFileInput(
                attrs={
                    "class": "form-control",
                }
            ),
        }
        help_texts = {
            "estado": "Si marcas ACTIVO, se validan datos mínimos (RFID/arete, sexo, etapa y potrero).",
            "potrero": "Potrero/lote actual donde se encuentra el animal.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Potreros activos por defecto (RN-4), manteniendo el actual aunque esté inactivo
        qs = Potrero.objects.filter(activo=True)
        if self.instance.pk and self.instance.potrero_id and self.instance.potrero not in qs:
            qs = Potrero.objects.filter(pk=self.instance.potrero_id) | qs

        self.fields["potrero"].queryset = qs.order_by("nombre")
        self.fields["potrero"].empty_label = "Seleccione un potrero"

        # Etiquetas más amigables
        self.fields["rfid"].label = "RFID"
        self.fields["arete"].label = "Nombre/Alias o Nº de arete"
        self.fields["fecha_nacimiento"].label = "Fecha de nacimiento"
        self.fields["motivo_baja"].label = "Motivo de baja"
