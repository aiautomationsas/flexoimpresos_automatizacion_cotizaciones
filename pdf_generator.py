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

        # Preparar el logo
        logo = Image("assests/logo_flexoimpresos.png")
        logo.drawHeight = 1.5 * inch
        logo.drawWidth = 2 * inch

        # Encabezado
        header_data = [
            [logo, 'FLEXO IMPRESOS S.A.S.'],
            ['', 'NIT: 901.297.493-1'],
            ['', 'Calle 79 Sur # 47 G 21'],
            ['', 'La Estrella - Antioquia'],
            ['', 'Tel: (604) 604 0404']
        ]
        
        header_table = Table(header_data, colWidths=[2.5*inch, 3.5*inch])
        header_table.setStyle(TableStyle([
            ('ALIGN', (0,0), (0,-1), 'CENTER'),  # Centrar logo
            ('ALIGN', (1,0), (1,-1), 'LEFT'),    # Alinear texto a la izquierda
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'), # Alineación vertical al medio
            ('FONTNAME', (1,0), (1,-1), 'Helvetica-Bold'),
            ('FONTSIZE', (1,0), (1,-1), 10),
            ('SPAN', (0,0), (0,4))  # Hacer que el logo ocupe todas las filas (0 a 4)
        ]))
        elements.append(header_table)
        elements.append(Spacer(1, 20))

        # Identificador (ahora separado del encabezado)
        elements.append(Paragraph('Identificador', self.styles['Normal']))
        elements.append(Spacer(1, 10))

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
        elements.append(Paragraph(f"Identificador: {datos_cotizacion['identificador']}", self.styles['Normal']))
        elements.append(Paragraph(f"Material: {datos_cotizacion['material']}", self.styles['Normal']))
        
        # Solo mostrar el adhesivo si es diferente a "No aplica"
        adhesivo = datos_cotizacion.get('adhesivo_tipo', 'No aplica')
        if adhesivo != "No aplica":
            elements.append(Paragraph(f"Adhesivo: {adhesivo.upper()}", self.styles['Normal']))
        
        # Solo mostrar acabado si no es manga
        if not datos_cotizacion.get('es_manga'):
            elements.append(Paragraph(f"Acabado: {datos_cotizacion['acabado']}", self.styles['Normal']))
        
        elements.append(Paragraph(f"Tintas: {datos_cotizacion['num_tintas']}", self.styles['Normal']))
        
        # Modificar el texto según sea etiqueta o manga
        if datos_cotizacion.get('es_manga'):
            elements.append(Paragraph(f"MT X PAQUETE: {datos_cotizacion['num_rollos']:,}", self.styles['Normal']))
        else:
            elements.append(Paragraph(f"ET X ROLLO: {datos_cotizacion['num_rollos']:,}", self.styles['Normal']))
        
        # Agregar tipo de grafado si es manga
        if datos_cotizacion.get('es_manga') and datos_cotizacion.get('tipo_grafado'):
            elements.append(Paragraph(f"Grafado: {datos_cotizacion['tipo_grafado']}", self.styles['Normal']))
        
        # Si no se incluyen planchas, mostrar "Planchas por separado" con el valor original
        if datos_cotizacion['valor_plancha_separado'] and not datos_cotizacion.get('es_manga'):
            elements.append(Paragraph(f"Planchas por separado: ${datos_cotizacion['valor_plancha_separado']:,.0f}", self.styles['Normal']))
        
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

        elements.append(Paragraph("Política de Entrega:", self.styles['Heading2']))
        elements.append(Paragraph("• Repeticiones: 13 días calendario a partir de la confirmación del pedido", self.styles['Normal']))
        elements.append(Paragraph("• Cambios: 15 días calendario a partir de la aprobación del sherpa", self.styles['Normal']))
        elements.append(Paragraph("• Nuevos: 20 días calendario a partir de la aprobación del sherpa", self.styles['Normal']))
        
        elements.append(Spacer(1, 10))
        elements.append(Paragraph("Política de Cobranza:", self.styles['Heading2']))
        elements.append(Paragraph("• Se retiene despacho con mora de 16 a 30 días", self.styles['Normal']))
        elements.append(Paragraph("• Se retiene producción con mora de 31 a 45 días", self.styles['Normal']))
        
        elements.append(Spacer(1, 10))
        elements.append(Paragraph("Vigencia de la cotización: 30 días", self.styles['Normal']))
        
        # Agregar firma del comercial
        if datos_cotizacion.get('comercial_nombre'):
            elements.append(Spacer(1, 40))  # Espacio adicional antes de la firma
            
            # Crear estilo para la firma
            firma_style = ParagraphStyle(
                'Firma',
                parent=self.styles['Normal'],
                alignment=1,  # Centrado
                spaceAfter=6  # Espacio después de cada línea
            )
            
            # Agregar datos del comercial
            elements.append(Paragraph(datos_cotizacion['comercial_nombre'].upper(), firma_style))
            if datos_cotizacion.get('comercial_email'):
                elements.append(Paragraph(datos_cotizacion['comercial_email'], firma_style))
            if datos_cotizacion.get('comercial_telefono'):
                elements.append(Paragraph(f"Cel {datos_cotizacion['comercial_telefono']}", firma_style))

        # Generar PDF
        doc.build(elements) 