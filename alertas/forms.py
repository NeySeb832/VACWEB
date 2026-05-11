from django import forms
from .models import ReglaAlerta


class AtenderAlertaForm(forms.Form):
    observacion = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 3, "class": "form-control", "placeholder": "Observación (opcional)"}),
        label="Observación",
    )


class ReglaAlertaForm(forms.ModelForm):
    class Meta:
        model = ReglaAlerta
        fields = ["activa", "umbral_valor", "umbral_unidad", "descripcion"]
        widgets = {
            "activa": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "umbral_valor": forms.NumberInput(attrs={"class": "form-control form-control-sm", "step": "0.1"}),
            "umbral_unidad": forms.TextInput(attrs={"class": "form-control form-control-sm"}),
            "descripcion": forms.Textarea(attrs={"class": "form-control form-control-sm", "rows": 2}),
        }
