from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from datetime import datetime
import math

class CotizacionPDF:
    def __init__(self):
        self.styles = getSampleStyleSheet()
        self.width, self.height = letter

    def _ajustar_valor_plancha(self, valor: float) -> float:
        """
        Aplica la fórmula =REDONDEAR.MAS(valor/0.75;-3) al valor de la plancha
        """
        valor_ajustado = valor / 0.75
        # Redondear hacia arriba al siguiente múltiplo de 1000
        return math.ceil(valor_ajustado / 1000) * 1000

    def generar_pdf(self, datos_cotizacion, path_salida):
        """
        Genera el PDF de la cotización
        """
        doc = SimpleDocTemplate(
            path_salida,
            pagesize=letter,
            rightMargin=72,
            leftMargin=72,
            topMargin=72,
            bottomMargin=72
        )

        # Contenedor para los elementos del PDF
        elements = []

        # Agregar el logo
        logo = Image("assests/logo_flexoimpresos.png")  # Cambia esto a la ruta de tu logo
        logo.drawHeight = 1.5 * inch
        logo.drawWidth = 2 * inch
        elements.append(logo)
        elements.append(Spacer(1, 20))

        # Encabezado
        header_data = [
            ['FLEXO IMPRESOS S.A.S.', ''],
            ['Nit: 900.528.680-0', f'COTIZACION'],
            ['Dirección: Calle 28A # 65A - 9', f'CTZ{datos_cotizacion["consecutivo"]:08d}'],
            ['Medellín, Colombia', ''],
            ['Teléfono: 57 (604) 4449661', ''],
            ['www.flexoimpresos.com', '']
        ]
        
        header_table = Table(header_data, colWidths=[4*inch, 2*inch])
        header_table.setStyle(TableStyle([
            ('ALIGN', (0,0), (-1,-1), 'LEFT'),
            ('FONTNAME', (0,0), (-1,-1), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,-1), 10),
        ]))
        elements.append(header_table)
        elements.append(Spacer(1, 20))

        # Fecha y cliente
        fecha = datetime.now().strftime("%d/%m/%Y")
        elements.append(Paragraph(f"Medellín, {fecha}", self.styles['Normal']))
        elements.append(Spacer(1, 10))
        elements.append(Paragraph(f"Señores:", self.styles['Normal']))
        elements.append(Paragraph(datos_cotizacion['cliente'], self.styles['Normal']))
        elements.append(Spacer(1, 20))

        # Asunto y detalles
        elements.append(Paragraph(f"Asunto: Cotización {datos_cotizacion['referencia']}", self.styles['Normal']))
        elements.append(Spacer(1, 10))
        elements.append(Paragraph(f"Etiquetas: {datos_cotizacion['identificador']}", self.styles['Normal']))
        elements.append(Paragraph(f"Material: {datos_cotizacion['material']}", self.styles['Normal']))
        elements.append(Paragraph(f"Adhesivo: PERMANENTE", self.styles['Normal']))
        elements.append(Paragraph(f"Terminación: {datos_cotizacion['acabado']}", self.styles['Normal']))
        elements.append(Paragraph(f"Tintas: {datos_cotizacion['num_tintas']}", self.styles['Normal']))
        elements.append(Paragraph(f"ET X ROLLO: {datos_cotizacion['num_rollos']:,}", self.styles['Normal']))
        
        # Agregar tipo de grafado si es manga
        if datos_cotizacion.get('es_manga') and datos_cotizacion.get('tipo_grafado'):
            elements.append(Paragraph(f"Grafado: {datos_cotizacion['tipo_grafado']}", self.styles['Normal']))
        
        if datos_cotizacion['valor_plancha_separado']:
            valor_ajustado = self._ajustar_valor_plancha(datos_cotizacion['valor_plancha_separado'])
            elements.append(Paragraph(f"Planchas por separado: ${valor_ajustado:,.0f}", self.styles['Normal']))
        
        elements.append(Spacer(1, 20))

        # Tabla de precios
        precio_headers = ['Escala', '$/U']
        precio_data = [precio_headers]
        for r in datos_cotizacion['resultados']:
            precio_data.append([
                f"{r['escala']:,}",
                f"${r['valor_unidad']:,.2f}"
            ])

        precio_table = Table(precio_data, colWidths=[2*inch, 1.5*inch])
        precio_table.setStyle(TableStyle([
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,-1), 10),
            ('GRID', (0,0), (-1,-1), 1, colors.black),
            ('BACKGROUND', (0,0), (-1,0), colors.lightgrey),
        ]))
        elements.append(precio_table)
        elements.append(Spacer(1, 20))

        # Políticas y condiciones
        elements.append(Paragraph("Forma de Pago: 50% ANTICIPO 50% ENTREGA", self.styles['Normal']))
        elements.append(Paragraph("I.V.A (no incluido): 19%", self.styles['Normal']))
        elements.append(Paragraph("% de Tolerancia: 10% + ó - de acuerdo a la cantidad pedida", self.styles['Normal']))
        elements.append(Spacer(1, 20))

        elements.append(Paragraph("Política de entrega:", self.styles['Normal']))
        elements.append(Paragraph("Repeticiones: 8 días calendario desde el envío de la OC", self.styles['Normal']))
        elements.append(Paragraph("Cambios: 13 días calendario desde la aprobación de la sherpa", self.styles['Normal']))
        elements.append(Paragraph("Nuevas: 15 días calendario desde la aprobación de la sherpa", self.styles['Normal']))
        elements.append(Spacer(1, 20))

        elements.append(Paragraph("Política de cartera:", self.styles['Normal']))
        elements.append(Paragraph("Se retiene el despacho con una mora de 16 a 30 días", self.styles['Normal']))
        elements.append(Paragraph("Se retiene producción con una mora de 31 a 45 días", self.styles['Normal']))

        # Generar PDF
        doc.build(elements) 