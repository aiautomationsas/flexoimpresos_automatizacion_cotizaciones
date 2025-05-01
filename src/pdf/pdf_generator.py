# src/pdf/pdf_generator.py
from dataclasses import dataclass
from typing import List, Dict, Optional, Any
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from ..data.models import Cotizacion, Escala, Cliente, ReferenciaCliente
import io
import tempfile
import os
import math
import traceback

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
    
    def generar_pdf(self, datos_cotizacion: Dict[str, Any]) -> Optional[bytes]:
        """
        Genera el PDF de la cotización y devuelve los bytes.
        
        Args:
            datos_cotizacion: Diccionario con todos los datos necesarios.
            
        Returns:
            Optional[bytes]: Los bytes del PDF generado o None si hay error.
        """
        print("\n=== DEBUG GENERAR_PDF (Bytes) ===")
        tmp_file = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
                doc = self._create_document(tmp_file.name)
                elements = []
                
                print(f"Generando PDF para cotización ID: {datos_cotizacion.get('id')}")
                
                elements.append(Paragraph(
                    f"Cotización #{datos_cotizacion.get('numero_cotizacion', 'N/A')}",
                    self.styles['CustomTitle']
                ))
                
                ref_cliente = datos_cotizacion.get('referencia_cliente')
                cliente = ref_cliente.get('cliente') if ref_cliente else None
                if cliente:
                    elements.extend(self._generar_seccion_cliente(cliente))
                else:
                    print("Advertencia: No hay datos de cliente para sección PDF.")
                    elements.append(Paragraph("Cliente no especificado", self.styles['Normal']))

                elements.extend(self._generar_seccion_producto(datos_cotizacion))

                escalas = datos_cotizacion.get('escalas')
                if escalas:
                    elements.extend(self._generar_tabla_escalas(escalas))
                else:
                    print("Advertencia: No hay datos de escalas para tabla PDF.")
                    elements.append(Paragraph("Escalas no disponibles", self.styles['Normal']))
                
                elements.extend(self._generar_seccion_tecnica(datos_cotizacion))

                doc.build(elements)
                print(f"PDF generado temporalmente en: {tmp_file.name}")

            with open(tmp_file.name, "rb") as f:
                pdf_bytes = f.read()
            print(f"Bytes del PDF leídos: {len(pdf_bytes)}")
            return pdf_bytes

        except Exception as e:
            print(f"Error fatal durante la generación de PDF en CotizacionPDF: {e}")
            traceback.print_exc()
            return None
        finally:
            if tmp_file and os.path.exists(tmp_file.name):
                try:
                    os.remove(tmp_file.name)
                    print(f"Archivo temporal eliminado: {tmp_file.name}")
                except Exception as e_del:
                    print(f"Error eliminando archivo temporal {tmp_file.name}: {e_del}")

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

def generar_bytes_pdf_cotizacion(datos_completos: Dict[str, Any]) -> Optional[bytes]:
    """
    Función helper para generar los bytes del PDF de cotización.
    Instancia CotizacionPDF y llama a su método generar_pdf.
    """
    if not datos_completos:
        print("Error: datos_completos son necesarios para generar PDF.")
        return None
    try:
        pdf_gen = CotizacionPDF() 
        pdf_bytes = pdf_gen.generar_pdf(datos_completos) 
        if pdf_bytes:
            print("Bytes de PDF generados exitosamente por la función helper.")
        else:
            print("La generación de PDF en CotizacionPDF devolvió None.")
        return pdf_bytes
    except Exception as e:
        print(f"Error en helper generar_bytes_pdf_cotizacion: {e}")
        traceback.print_exc() 
        return None