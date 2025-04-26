# src/pdf/pdf_generator.py
from dataclasses import dataclass
from typing import List, Dict, Optional
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from ..data.models import Cotizacion, Escala, Cliente, ReferenciaCliente

@dataclass
class PDFGenerationConfig:
    """Configuración para la generación de PDF"""
    page_size: tuple = letter
    margin: float = 40
    title_font_size: int = 16
    normal_font_size: int = 12
    table_style: List[tuple] = None

    def __post_init__(self):
        if self.table_style is None:
            self.table_style = [
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 12),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
                ('GRID', (0, 0), (-1, -1), 1, colors.black)
            ]

class BasePDFGenerator:
    """Clase base para la generación de PDFs"""
    def __init__(self, config: Optional[PDFGenerationConfig] = None):
        self.config = config or PDFGenerationConfig()
        self.styles = getSampleStyleSheet()
        self._setup_custom_styles()

    def _setup_custom_styles(self):
        """Configura estilos personalizados para el PDF"""
        self.styles.add(ParagraphStyle(
            name='CustomTitle',
            fontSize=self.config.title_font_size,
            spaceAfter=30,
            alignment=1  # Centro
        ))

    def _create_document(self, output_path: str) -> SimpleDocTemplate:
        """Crea el documento base con la configuración establecida"""
        return SimpleDocTemplate(
            output_path,
            pagesize=self.config.page_size,
            rightMargin=self.config.margin,
            leftMargin=self.config.margin,
            topMargin=self.config.margin,
            bottomMargin=self.config.margin
        )

class CotizacionPDF(BasePDFGenerator):
    """Generador de PDF para cotizaciones"""
    
    def generar_pdf(self, cotizacion: Cotizacion, output_path: str) -> None:
        """
        Genera el PDF de la cotización
        
        Args:
            cotizacion: Objeto Cotizacion con todos los datos necesarios
            output_path: Ruta donde se guardará el PDF
        """
        doc = self._create_document(output_path)
        elements = []
        
        # Agregar título
        elements.append(Paragraph(
            f"Cotización #{cotizacion.numero_cotizacion}",
            self.styles['CustomTitle']
        ))
        
        # Información del cliente
        elements.extend(self._generar_seccion_cliente(cotizacion.referencia_cliente.cliente))
        
        # Detalles del producto
        elements.extend(self._generar_seccion_producto(cotizacion))
        
        # Tabla de escalas
        elements.extend(self._generar_tabla_escalas(cotizacion.escalas))
        
        # Información técnica
        elements.extend(self._generar_seccion_tecnica(cotizacion))
        
        # Generar el PDF
        doc.build(elements)

    def _generar_seccion_cliente(self, cliente: Cliente) -> List:
        """Genera la sección de información del cliente"""
        elements = []
        # Implementar la generación de la sección del cliente
        return elements

    def _generar_seccion_producto(self, cotizacion: Cotizacion) -> List:
        """Genera la sección de detalles del producto"""
        elements = []
        # Implementar la generación de la sección del producto
        return elements

    def _generar_tabla_escalas(self, escalas: List[Escala]) -> List:
        """Genera la tabla de escalas de producción"""
        elements = []
        # Implementar la generación de la tabla de escalas
        return elements

    def _generar_seccion_tecnica(self, cotizacion: Cotizacion) -> List:
        """Genera la sección de información técnica"""
        elements = []
        # Implementar la generación de la sección técnica
        return elements

class MaterialesPDF(BasePDFGenerator):
    """Generador de PDF para información de materiales"""
    
    def generar_pdf(self, cotizacion: Cotizacion, output_path: str) -> None:
        """
        Genera el PDF de materiales
        
        Args:
            cotizacion: Objeto Cotizacion con todos los datos necesarios
            output_path: Ruta donde se guardará el PDF
        """
        doc = self._create_document(output_path)
        elements = []
        
        # Título
        elements.append(Paragraph(
            f"Información de Materiales - Cotización #{cotizacion.numero_cotizacion}",
            self.styles['CustomTitle']
        ))
        
        # Detalles de materiales
        elements.extend(self._generar_seccion_materiales(cotizacion))
        
        # Especificaciones técnicas
        elements.extend(self._generar_especificaciones_tecnicas(cotizacion))
        
        # Generar el PDF
        doc.build(elements)

    def _generar_seccion_materiales(self, cotizacion: Cotizacion) -> List:
        """Genera la sección de detalles de materiales"""
        elements = []
        # Implementar la generación de la sección de materiales
        return elements

    def _generar_especificaciones_tecnicas(self, cotizacion: Cotizacion) -> List:
        """Genera la sección de especificaciones técnicas"""
        elements = []
        # Implementar la generación de la sección de especificaciones
        return elements