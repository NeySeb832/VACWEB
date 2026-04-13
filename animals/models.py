from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

class Potrero(models.Model):
    """Potrero/Lote para movimientos. RN-4: solo destinos activos."""
    nombre = models.CharField(max_length=64, unique=True)
    activo = models.BooleanField(default=True)

    def __str__(self) -> str:
        return self.nombre


class Animal(models.Model):
    """CU-002: Animal con identificadores y estado de ciclo de vida.
    Post: RN-3 baja lógica; RN-2 datos mínimos para estado 'ACTIVO'.
    """
    class Sexo(models.TextChoices):
        MACHO = "M", "Macho"
        HEMBRA = "F", "Hembra"

    class Etapa(models.TextChoices):
        TERNERO = "TER", "Ternero"
        DESTETE = "DES", "Destete"
        LEVANTE = "LEV", "Levante/Ceba"
        NOVILLO = "NOV", "Novillo"
        ADULTO = "ADU", "Adulto"

    class Estado(models.TextChoices):
        ACTIVO = "ACT", "Activo"
        INACTIVO = "INA", "Inactivo"      # baja lógica
        BORRADOR = "BOR", "Borrador"      # RN-2 si faltan datos mínimos

    rfid = models.CharField(max_length=32, blank=True, null=True, unique=True)
    arete = models.CharField(max_length=32, blank=True, null=True, unique=True)
    sexo = models.CharField(max_length=1, choices=Sexo.choices, blank=True, null=True)
    etapa = models.CharField(max_length=3, choices=Etapa.choices, blank=True, null=True)
    raza = models.CharField(max_length=48, blank=True, null=True)
    fecha_nacimiento = models.DateField(blank=True, null=True)
    potrero = models.ForeignKey(Potrero, on_delete=models.PROTECT, related_name="animales", blank=True, null=True)

    estado = models.CharField(max_length=3, choices=Estado.choices, default=Estado.BORRADOR)
    motivo_baja = models.CharField(max_length=64, blank=True, null=True)

    foto = models.ImageField(
        upload_to="animals/fotos/",
        blank=True,
        null=True,
    )
    # Auditoría mínima (RN-5)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_modified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.rfid or self.arete or 'SIN-ID'}"

    # RN-2: si estado ACTIVO → debe tener mínimos
    def clean(self):
        # RN-2: estado ACTIVO requiere datos mínimos
        if self.estado == self.Estado.ACTIVO:
            missing = []
            if not (self.rfid or self.arete):
                missing.append("RFID/Arete")
            if not self.sexo:
                missing.append("Sexo")
            if not self.etapa:
                missing.append("Etapa")
            if not self.potrero_id:
                missing.append("Potrero")
            if missing:
                raise ValidationError(
                    {"__all__": f"Para estado ACTIVO faltan: {', '.join(missing)}"}
                )

        # RN-1: RFID y Arete son inmutables si el animal ya tiene historial
        if self.pk:
            try:
                prev = Animal.objects.get(pk=self.pk)
            except Animal.DoesNotExist:
                pass
            else:
                if prev.tiene_historial:
                    errores = {}
                    if prev.rfid != self.rfid:
                        errores["rfid"] = (
                            "RN-1: No se puede modificar el RFID de un animal con historial."
                        )
                    if prev.arete != self.arete:
                        errores["arete"] = (
                            "RN-1: No se puede modificar el Arete de un animal con historial."
                        )
                    if errores:
                        raise ValidationError(errores)

        return super().clean()

    @property
    def tiene_historial(self) -> bool:
        return self.eventos.exists() or self.movimientos.exists()


class Movimiento(models.Model):
    """RN-4: Movimiento entre potreros válidos y activos."""
    animal = models.ForeignKey(Animal, on_delete=models.CASCADE, related_name="movimientos")
    desde = models.ForeignKey(Potrero, on_delete=models.PROTECT, related_name="+", blank=True, null=True)
    hacia = models.ForeignKey(Potrero, on_delete=models.PROTECT, related_name="+")
    fecha = models.DateField(default=timezone.now)
    responsable = models.CharField(max_length=64)

    def clean(self):
        if self.hacia and not self.hacia.activo:
            raise ValidationError("El potrero destino no está activo.")
        if self.desde_id and self.desde_id == self.hacia_id:
            raise ValidationError("El potrero de destino debe ser diferente al origen.")
        return super().clean()

    def __str__(self) -> str:
        return f"{self.animal} → {self.hacia} ({self.fecha:%Y-%m-%d})"


