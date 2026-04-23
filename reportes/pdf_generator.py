# reportes/pdf_generator.py
"""
Generador de PDFs profesionales para el módulo de Reportes (CU-007).
Produce documentos con cabecera institucional SIGAN, sección de KPIs
y tabla de datos completa, siguiendo el diseño especificado en el análisis.
"""
from datetime import date as _date
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    HRFlowable,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

# ── Paleta de colores SIGAN ───────────────────────────────────────────────────
COLOR_VERDE_OSCURO  = colors.HexColor("#1a4d2e")   # cabecera principal
COLOR_VERDE_MEDIO   = colors.HexColor("#2d6a4f")   # banda secundaria
COLOR_VERDE_CLARO   = colors.HexColor("#d8f3dc")   # fondo KPI
COLOR_TEXTO_OSCURO  = colors.HexColor("#111827")
COLOR_TEXTO_GRIS    = colors.HexColor("#6b7280")
COLOR_BORDE_TABLA   = colors.HexColor("#d1d5db")
COLOR_HEADER_TABLA  = colors.HexColor("#1a4d2e")
COLOR_FILA_PAR      = colors.HexColor("#f9fafb")
COLOR_FILA_IMPAR    = colors.white
COLOR_ACCENT        = colors.HexColor("#52b788")

PAGE_W, PAGE_H = A4
MARGIN = 1.8 * cm


# ── Estilos de texto ─────────────────────────────────────────────────────────

def _build_styles():
    base = getSampleStyleSheet()
    estilos = {
        "titulo_doc": ParagraphStyle(
            "titulo_doc", parent=base["Normal"],
            fontSize=18, fontName="Helvetica-Bold",
            textColor=colors.white, alignment=TA_LEFT,
            spaceAfter=2,
        ),
        "subtitulo_doc": ParagraphStyle(
            "subtitulo_doc", parent=base["Normal"],
            fontSize=9, fontName="Helvetica",
            textColor=colors.HexColor("#a7f3d0"), alignment=TA_LEFT,
        ),
        "meta_derecha": ParagraphStyle(
            "meta_derecha", parent=base["Normal"],
            fontSize=8, fontName="Helvetica",
            textColor=colors.white, alignment=TA_RIGHT,
        ),
        "seccion": ParagraphStyle(
            "seccion", parent=base["Normal"],
            fontSize=10, fontName="Helvetica-Bold",
            textColor=COLOR_VERDE_OSCURO, spaceBefore=12, spaceAfter=6,
        ),
        "kpi_label": ParagraphStyle(
            "kpi_label", parent=base["Normal"],
            fontSize=7, fontName="Helvetica",
            textColor=COLOR_TEXTO_GRIS, alignment=TA_CENTER,
        ),
        "kpi_valor": ParagraphStyle(
            "kpi_valor", parent=base["Normal"],
            fontSize=18, fontName="Helvetica-Bold",
            textColor=COLOR_VERDE_OSCURO, alignment=TA_CENTER,
        ),
        "kpi_sub": ParagraphStyle(
            "kpi_sub", parent=base["Normal"],
            fontSize=7, fontName="Helvetica",
            textColor=COLOR_TEXTO_GRIS, alignment=TA_CENTER,
        ),
        "pie_pagina": ParagraphStyle(
            "pie_pagina", parent=base["Normal"],
            fontSize=7, fontName="Helvetica",
            textColor=COLOR_TEXTO_GRIS, alignment=TA_CENTER,
        ),
        "nota": ParagraphStyle(
            "nota", parent=base["Normal"],
            fontSize=7.5, fontName="Helvetica-Oblique",
            textColor=COLOR_TEXTO_GRIS,
        ),
        "normal": ParagraphStyle(
            "p_normal", parent=base["Normal"],
            fontSize=8, fontName="Helvetica",
            textColor=COLOR_TEXTO_OSCURO,
        ),
    }
    return estilos


# ── Cabecera y pie de página ─────────────────────────────────────────────────

def _on_page(canvas, doc, meta: dict):
    """Dibuja la cabecera institucional y el pie en cada página."""
    st = _build_styles()
    canvas.saveState()
    w, h = doc.pagesize

    # ── Banda verde superior ──────────────────────────────────────────────────
    BAND_H = 2.6 * cm
    canvas.setFillColor(COLOR_VERDE_OSCURO)
    canvas.rect(0, h - BAND_H, w, BAND_H, fill=1, stroke=0)

    # Acento lateral izquierdo
    canvas.setFillColor(COLOR_ACCENT)
    canvas.rect(0, h - BAND_H, 0.45 * cm, BAND_H, fill=1, stroke=0)

    # Texto cabecera
    canvas.setFont("Helvetica-Bold", 16)
    canvas.setFillColor(colors.white)
    canvas.drawString(0.9 * cm, h - 1.45 * cm, "SIGAN")

    canvas.setFont("Helvetica", 9)
    canvas.setFillColor(colors.HexColor("#a7f3d0"))
    canvas.drawString(0.9 * cm, h - 1.95 * cm, meta.get("subtitulo", "Sistema de Gestión Animal"))

    # Bloque derecho: tipo de reporte + metadatos
    linea1 = meta.get("tipo_reporte", "").upper()
    linea2 = f"Finca: {meta.get('finca', '')}   Período: {meta.get('periodo', '')}"
    linea3 = f"Generado: {meta.get('fecha_gen', '')}   Usuario: {meta.get('usuario', '')}"

    canvas.setFont("Helvetica-Bold", 10)
    canvas.setFillColor(colors.white)
    canvas.drawRightString(w - 0.9 * cm, h - 1.15 * cm, linea1)

    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(colors.HexColor("#d1fae5"))
    canvas.drawRightString(w - 0.9 * cm, h - 1.65 * cm, linea2)
    canvas.drawRightString(w - 0.9 * cm, h - 2.10 * cm, linea3)

    # ── Línea separadora bajo la cabecera ─────────────────────────────────────
    canvas.setStrokeColor(COLOR_VERDE_MEDIO)
    canvas.setLineWidth(1.5)
    canvas.line(0, h - BAND_H - 0.06 * cm, w, h - BAND_H - 0.06 * cm)

    # ── Pie de página ─────────────────────────────────────────────────────────
    canvas.setStrokeColor(COLOR_BORDE_TABLA)
    canvas.setLineWidth(0.5)
    canvas.line(MARGIN, 1.4 * cm, w - MARGIN, 1.4 * cm)

    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(COLOR_TEXTO_GRIS)
    canvas.drawString(MARGIN, 0.9 * cm,
                      f"SIGAN · {meta.get('tipo_reporte', '')} · Confidencial")
    canvas.drawCentredString(w / 2, 0.9 * cm,
                             f"Página {doc.page} de <N>")
    canvas.drawRightString(w - MARGIN, 0.9 * cm,
                           f"Generado el {meta.get('fecha_gen', '')}")

    canvas.restoreState()


def _on_page_later(canvas, doc, meta: dict):
    """Igual que _on_page pero marca páginas posteriores."""
    _on_page(canvas, doc, meta)


# ── Tabla de KPIs ─────────────────────────────────────────────────────────────

def _tabla_kpis(kpis: list[dict], estilos: dict, ancho: float) -> Table:
    """
    Recibe una lista de dicts con claves: label, valor, sub.
    Devuelve una Table con celdas KPI con fondo verde claro.
    """
    n = len(kpis)
    col_w = (ancho - (n - 1) * 0.3 * cm) / n

    datos = [[
        Table(
            [
                [Paragraph(k["label"].upper(), estilos["kpi_label"])],
                [Paragraph(str(k["valor"]), estilos["kpi_valor"])],
                [Paragraph(k.get("sub", ""), estilos["kpi_sub"])],
            ],
            colWidths=[col_w - 0.6 * cm],
            style=TableStyle([
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]),
        )
        for k in kpis
    ]]

    col_widths = [col_w] * n
    tbl = Table(datos, colWidths=col_widths, rowHeights=[2.4 * cm])
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), COLOR_VERDE_CLARO),
        ("BOX", (0, 0), (-1, -1), 0.75, COLOR_VERDE_OSCURO),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, COLOR_VERDE_MEDIO),
        ("ROUNDEDCORNERS", [6]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ]))
    return tbl


# ── Tabla de datos ────────────────────────────────────────────────────────────

def _tabla_datos(encabezados: list, filas: list[list], col_widths: list,
                 estilos: dict) -> Table:
    """Construye la tabla de datos con cabecera verde y filas alternadas."""
    st = estilos["normal"]

    # Cabecera
    hdr_style = ParagraphStyle(
        "hdr", fontSize=7.5, fontName="Helvetica-Bold",
        textColor=colors.white, alignment=TA_CENTER,
    )
    hdr_row = [Paragraph(h, hdr_style) for h in encabezados]

    # Filas de datos
    rows_fmt = []
    for i, fila in enumerate(filas):
        color_bg = COLOR_FILA_PAR if i % 2 == 0 else COLOR_FILA_IMPAR
        row_fmt = [Paragraph(str(c) if c is not None else "—", st) for c in fila]
        rows_fmt.append(row_fmt)

    all_rows = [hdr_row] + rows_fmt
    tbl = Table(all_rows, colWidths=col_widths, repeatRows=1)

    style = TableStyle([
        # Cabecera
        ("BACKGROUND", (0, 0), (-1, 0), COLOR_HEADER_TABLA),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ALIGN", (0, 0), (-1, 0), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 7.5),
        ("TOPPADDING", (0, 0), (-1, 0), 7),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 7),
        # Filas
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 1), (-1, -1), 7.5),
        ("TOPPADDING", (0, 1), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        # Bordes
        ("GRID", (0, 0), (-1, -1), 0.4, COLOR_BORDE_TABLA),
        ("LINEBELOW", (0, 0), (-1, 0), 1.5, COLOR_VERDE_OSCURO),
        # Alternado
        *[
            ("BACKGROUND", (0, i + 1), (-1, i + 1),
             COLOR_FILA_PAR if i % 2 == 0 else COLOR_FILA_IMPAR)
            for i in range(len(rows_fmt))
        ],
    ])
    tbl.setStyle(style)
    return tbl


# ── Constructor base del documento ───────────────────────────────────────────

def _build_doc(buffer: BytesIO, meta: dict, orientacion="portrait") -> BaseDocTemplate:
    pagesize = landscape(A4) if orientacion == "landscape" else A4
    doc = BaseDocTemplate(
        buffer,
        pagesize=pagesize,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=3.5 * cm,   # espacio para cabecera
        bottomMargin=2.0 * cm,
    )
    frame = Frame(
        doc.leftMargin, doc.bottomMargin,
        doc.width, doc.height,
        id="principal",
    )
    doc.addPageTemplates([
        PageTemplate(
            id="principal",
            frames=[frame],
            onPage=lambda c, d: _on_page(c, d, meta),
        )
    ])
    return doc


def _separador(estilos: dict, texto: str) -> list:
    """Devuelve una lista de flowables para separar secciones."""
    return [
        Spacer(1, 0.4 * cm),
        Paragraph(texto, estilos["seccion"]),
        HRFlowable(width="100%", thickness=1, color=COLOR_VERDE_MEDIO,
                   spaceAfter=6),
    ]


# ── 1. PDF Inventario ─────────────────────────────────────────────────────────

def generar_pdf_inventario(animals_data: list, kpi: dict, meta: dict) -> bytes:
    """
    animals_data: lista de dicts con keys animal, peso_actual, dias_en_finca
    kpi: dict con total, machos, hembras, peso_promedio
    meta: dict con finca, periodo, fecha_gen, usuario
    """
    meta.setdefault("tipo_reporte", "Reporte de Inventario de Animales")
    meta.setdefault("subtitulo", "Control de Inventario Ganadero")

    buffer = BytesIO()
    doc = _build_doc(buffer, meta)
    st = _build_styles()
    ancho = doc.width

    story = []

    # KPIs
    story += _separador(st, "Indicadores Clave (KPIs)")
    kpis = [
        {"label": "Total animales",  "valor": kpi.get("total", 0),   "sub": "en inventario"},
        {"label": "Machos",          "valor": kpi.get("machos", 0),  "sub": "cabezas"},
        {"label": "Hembras",         "valor": kpi.get("hembras", 0), "sub": "cabezas"},
        {"label": "Peso promedio",
         "valor": f"{kpi['peso_promedio']:.1f} kg" if kpi.get("peso_promedio") else "N/D",
         "sub": "último pesaje"},
    ]
    story.append(_tabla_kpis(kpis, st, ancho))

    # Tabla de datos
    story += _separador(st, f"Detalle de Animales — {kpi.get('total', 0)} registros")

    encabezados = ["RFID", "Raza", "Sexo", "Nacimiento", "Lote / Potrero",
                   "Peso (kg)", "Días en finca", "Estado"]
    col_w = [ancho * p for p in [0.15, 0.13, 0.08, 0.11, 0.16, 0.10, 0.12, 0.15]]

    filas = []
    for d in animals_data:
        a = d["animal"]
        filas.append([
            a.rfid or a.nombre or "—",
            a.raza or "—",
            a.get_sexo_display() if a.sexo else "—",
            a.fecha_nacimiento.strftime("%d/%m/%Y") if a.fecha_nacimiento else "—",
            str(a.potrero) if a.potrero else "—",
            f"{float(d['peso_actual']):.1f}" if d["peso_actual"] else "—",
            str(d["dias_en_finca"]) if d["dias_en_finca"] is not None else "—",
            a.get_estado_display(),
        ])

    if filas:
        story.append(_tabla_datos(encabezados, filas, col_w, st))
    else:
        story.append(Paragraph("No se encontraron registros con los filtros aplicados.",
                                st["nota"]))

    story.append(Spacer(1, 0.5 * cm))
    story.append(Paragraph(
        "* El peso mostrado corresponde al último pesaje registrado para cada animal. "
        "Reporte generado en tiempo real — RN-3 SIGAN.",
        st["nota"],
    ))

    doc.build(story)
    return buffer.getvalue()


# ── 2. PDF Historial por Animal ───────────────────────────────────────────────

def generar_pdf_historial(animals_data: list, kpi: dict, meta: dict) -> bytes:
    """
    animals_data: lista de dicts con keys animal, n_eventos, n_pesajes, n_movs
    kpi: dict con total_animales, total_eventos, total_pesajes
    """
    meta.setdefault("tipo_reporte", "Reporte de Historial por Animal")
    meta.setdefault("subtitulo", "Trazabilidad Individual de Animales")

    buffer = BytesIO()
    doc = _build_doc(buffer, meta)
    st = _build_styles()
    ancho = doc.width

    story = []

    # KPIs
    story += _separador(st, "Indicadores Clave (KPIs)")
    kpis = [
        {"label": "Total animales",       "valor": kpi.get("total_animales", 0), "sub": "en el período"},
        {"label": "Eventos sanitarios",   "valor": kpi.get("total_eventos", 0),  "sub": "registrados"},
        {"label": "Pesajes registrados",  "valor": kpi.get("total_pesajes", 0),  "sub": "en el período"},
    ]
    story.append(_tabla_kpis(kpis, st, ancho))

    # Tabla
    story += _separador(st, f"Historial por Animal — {kpi.get('total_animales', 0)} registros")

    encabezados = ["RFID / Arete", "Raza", "Lote / Potrero", "Estado",
                   "Eventos sanitarios", "Pesajes", "Movimientos"]
    col_w = [ancho * p for p in [0.18, 0.13, 0.17, 0.13, 0.16, 0.12, 0.11]]

    filas = []
    for d in animals_data:
        a = d["animal"]
        filas.append([
            a.rfid or a.nombre or "—",
            a.raza or "—",
            str(a.potrero) if a.potrero else "—",
            a.get_estado_display(),
            str(d["n_eventos"]),
            str(d["n_pesajes"]),
            str(d["n_movs"]),
        ])

    if filas:
        story.append(_tabla_datos(encabezados, filas, col_w, st))
    else:
        story.append(Paragraph("No se encontraron registros con los filtros aplicados.",
                                st["nota"]))

    story.append(Spacer(1, 0.5 * cm))
    story.append(Paragraph(
        "* Los conteos de eventos, pesajes y movimientos corresponden al rango de fechas seleccionado. "
        "Reporte generado en tiempo real — RN-3 SIGAN.",
        st["nota"],
    ))

    doc.build(story)
    return buffer.getvalue()


# ── 3. PDF Sanitario ─────────────────────────────────────────────────────────

def generar_pdf_sanitario(eventos: list, kpi: dict, meta: dict) -> bytes:
    """
    eventos: lista de objetos EventoSanitario con select_related("animal")
    kpi: dict con total_eventos, confirmados, aplazados
    """
    meta.setdefault("tipo_reporte", "Reporte de Calendario Sanitario")
    meta.setdefault("subtitulo", "Programación de Vacunas y Tratamientos")

    buffer = BytesIO()
    doc = _build_doc(buffer, meta, orientacion="landscape")
    st = _build_styles()
    ancho = doc.width

    story = []

    # KPIs
    story += _separador(st, "Indicadores Clave (KPIs)")
    kpis = [
        {"label": "Total eventos",  "valor": kpi.get("total_eventos", 0), "sub": "programados/aplicados"},
        {"label": "Confirmados",    "valor": kpi.get("confirmados", 0),   "sub": "pendientes"},
        {"label": "Aplazados",      "valor": kpi.get("aplazados", 0),     "sub": "reagendados"},
    ]
    story.append(_tabla_kpis(kpis, st, ancho))

    # Tabla
    story += _separador(st, f"Detalle de Eventos Sanitarios — {kpi.get('total_eventos', 0)} registros")

    encabezados = ["Fecha", "Animal (RFID/Arete)", "Lote / Potrero", "Tipo de evento",
                   "Producto / Vacuna", "Dosis", "Responsable", "Estado"]
    col_w = [ancho * p for p in [0.10, 0.15, 0.13, 0.14, 0.18, 0.08, 0.12, 0.10]]

    filas = []
    for e in eventos:
        animal_id = (e.animal.rfid or e.animal.nombre or "SIN-ID") if e.animal else "—"
        lote = str(e.animal.potrero) if e.animal and e.animal.potrero else "—"
        filas.append([
            e.fecha.strftime("%d/%m/%Y"),
            animal_id,
            lote,
            e.tipo,
            e.producto or "—",
            e.dosis or "—",
            e.responsable or "—",
            e.get_estado_display(),
        ])

    if filas:
        story.append(_tabla_datos(encabezados, filas, col_w, st))
    else:
        story.append(Paragraph("No se encontraron eventos sanitarios con los filtros aplicados.",
                                st["nota"]))

    story.append(Spacer(1, 0.5 * cm))
    story.append(Paragraph(
        "* Los eventos con estado 'Aplazado' requieren reagendamiento. "
        "Próximas aplicaciones deben verificarse con el médico veterinario. "
        "Reporte generado en tiempo real — RN-3 SIGAN.",
        st["nota"],
    ))

    doc.build(story)
    return buffer.getvalue()


# ── 4. PDF Ventas ─────────────────────────────────────────────────────────────

def generar_pdf_ventas(ventas: list, kpi: dict, meta: dict) -> bytes:
    """
    ventas: lista de objetos Transaccion con select_related("animal", "created_by")
    kpi: dict con total_ventas, peso_total, valor_total
    """
    meta.setdefault("tipo_reporte", "Reporte Comercial — Ventas")
    meta.setdefault("subtitulo", "Registro de Transacciones Comerciales")

    buffer = BytesIO()
    doc = _build_doc(buffer, meta, orientacion="landscape")
    st = _build_styles()
    ancho = doc.width

    story = []

    # KPIs
    story += _separador(st, "Indicadores Clave (KPIs)")
    valor_fmt = f"${kpi.get('valor_total', 0):,.0f} COP" if kpi.get("valor_total") else "$0 COP"
    kpis = [
        {"label": "Total ventas",          "valor": kpi.get("total_ventas", 0),
         "sub": "transacciones confirmadas"},
        {"label": "Peso total vendido",
         "valor": f"{kpi.get('peso_total', 0):.1f} kg" if kpi.get("peso_total") else "0 kg",
         "sub": "kilogramos"},
        {"label": "Valor total (informativo)", "valor": valor_fmt, "sub": "pesos colombianos"},
    ]
    story.append(_tabla_kpis(kpis, st, ancho))

    # Tabla
    story += _separador(st, f"Detalle de Ventas — {kpi.get('total_ventas', 0)} registros")

    encabezados = ["Fecha", "RFID / Arete", "Raza", "Lote / Potrero",
                   "Destino / Comprador", "Peso final (kg)", "Valor (COP)", "Registrado por"]
    col_w = [ancho * p for p in [0.10, 0.13, 0.10, 0.13, 0.20, 0.12, 0.13, 0.09]]

    filas = []
    for v in ventas:
        animal_id = (v.animal.rfid or v.animal.nombre or "SIN-ID") if v.animal else "—"
        raza = v.animal.raza if v.animal else "—"
        lote = str(v.animal.potrero) if v.animal and v.animal.potrero else "—"
        registrado = ""
        if v.created_by:
            registrado = v.created_by.get_full_name() or v.created_by.username
        valor_str = f"${float(v.valor_cop):,.0f}" if v.valor_cop else "—"
        filas.append([
            v.fecha.strftime("%d/%m/%Y"),
            animal_id,
            raza or "—",
            lote,
            v.origen_destino or "—",
            f"{float(v.peso_final_kg):.1f}" if v.peso_final_kg else "—",
            valor_str,
            registrado or "—",
        ])

    if filas:
        story.append(_tabla_datos(encabezados, filas, col_w, st))
    else:
        story.append(Paragraph("No se encontraron ventas confirmadas con los filtros aplicados.",
                                st["nota"]))

    story.append(Spacer(1, 0.5 * cm))
    story.append(Paragraph(
        "* El valor monetario mostrado es de carácter informativo. "
        "El sistema no realiza cálculos financieros ni contables (RN-7 SIGAN). "
        "Incluye únicamente transacciones de tipo VENTA en estado CONFIRMADO.",
        st["nota"],
    ))

    doc.build(story)
    return buffer.getvalue()


# ── Helper: construir metadatos del reporte ───────────────────────────────────

def construir_meta(request, tipo: str, desde_raw: str, hasta_raw: str,
                   subtitulo: str = "") -> dict:
    """Construye el dict de metadatos para el PDF a partir del request."""
    hoy = _date.today().strftime("%d/%m/%Y")
    if desde_raw and hasta_raw:
        periodo = f"{desde_raw} – {hasta_raw}"
    elif desde_raw:
        periodo = f"Desde {desde_raw}"
    elif hasta_raw:
        periodo = f"Hasta {hasta_raw}"
    else:
        periodo = "Todos los registros"

    usuario = request.user.get_full_name() or request.user.username

    # Intentar obtener el nombre de la finca desde la sesión o configuración
    finca = getattr(request, "finca_nombre", None) or "Finca registrada"
    try:
        from finca_ganadera.models import Finca
        finca_obj = Finca.objects.filter(activa=True).first()
        if finca_obj:
            finca = finca_obj.nombre
    except Exception:
        pass

    return {
        "tipo_reporte": tipo,
        "subtitulo":    subtitulo or "Sistema de Gestión Animal — SIGAN",
        "finca":        finca,
        "periodo":      periodo,
        "fecha_gen":    hoy,
        "usuario":      usuario,
    }
