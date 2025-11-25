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
                raise ValidationError(f"Para estado ACTIVO faltan: {', '.join(missing)}")

        # Si baja lógica → no permitir borrar identificadores, solo bloquear edición en lógica de negocio
        return super().clean()

    @property
    def tiene_historial(self) -> bool:
        return self.eventos.exists() or self.movimientos.exists() or self.pesajes.exists()


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


class EventoSanitario(models.Model):
    """Registro sanitario básico (vacunas/desparasitaciones)."""
    animal = models.ForeignKey(Animal, on_delete=models.CASCADE, related_name="eventos")
    tipo = models.CharField(max_length=64)         # p.ej. Vacuna Aftosa
    fecha = models.DateField(default=timezone.now)
    responsable = models.CharField(max_length=64)
    notas = models.TextField(blank=True, null=True)

    def clean(self):
        if not self.fecha or not self.responsable:
            raise ValidationError("Fecha y responsable son obligatorios.")
        return super().clean()

    def __str__(self) -> str:
        return f"{self.tipo} · {self.fecha:%Y-%m-%d}"


class Pesaje(models.Model):
    """Pesajes con fecha para indicadores de productividad."""
    animal = models.ForeignKey(Animal, on_delete=models.CASCADE, related_name="pesajes")
    fecha = models.DateField(default=timezone.now)
    peso_kg = models.DecimalField(max_digits=7, decimal_places=2)

    def __str__(self) -> str:
        return f"{self.peso_kg} kg · {self.fecha:%Y-%m-%d}"
