# src/pdf/pdf_generator.py
from dataclasses import dataclass
from typing import List, Dict, Optional, Any
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image, Flowable, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from ..data.models import Cotizacion, Escala, Cliente, ReferenciaCliente
import io
import tempfile
import os
import math
import traceback
from datetime import datetime
from decimal import Decimal

# Placeholder para EmptyImage si Image falla (como en el código provisto)
class EmptyImage(Flowable):
    def __init__(self, width, height):
        Flowable.__init__(self)
        self.width = width
        self.height = height
    def draw(self):
        pass

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
        # Añadir estilo para la firma
        self.styles.add(ParagraphStyle(
            name='FirmaStyle',
            fontSize=9,
            alignment=0 # Izquierda
        ))
        self.firma_style = self.styles['FirmaStyle'] # Guardar referencia

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
    
    def _crear_resultados_predeterminados(self) -> List[Dict[str, Any]]:
        """Crea una lista de resultados predeterminada si no se encuentran datos."""
        # Placeholder: Devuelve una lista vacía o con algún valor por defecto
        print("ADVERTENCIA: Llamando a _crear_resultados_predeterminados. Implementar lógica real si es necesario.")
        return [{'escala': 0, 'valor_unidad': 0.0}]
    
    def generar_pdf(self, datos_cotizacion: Dict[str, Any]) -> Optional[bytes]:
        """
        Genera el PDF de la cotización siguiendo la estructura provista.
        
        Args:
            datos_cotizacion: Diccionario con todos los datos necesarios.
            
        Returns:
            Optional[bytes]: Los bytes del PDF generado o None si hay error.
        """
        print("\n=== DEBUG GENERAR_PDF (Adaptado) ===")
        print("Datos recibidos para generar PDF:")
        # Simplificado para brevedad, puedes añadir más si es necesario
        print(f"  ID: {datos_cotizacion.get('id')}") 
        print(f"  Cliente: {datos_cotizacion.get('nombre_cliente')}") 
        print(f"  Consecutivo: {datos_cotizacion.get('consecutivo')}")
        
        tmp_file = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
                doc = self._create_document(tmp_file.name)
                elements = []
                
                # --- Inicio del código adaptado del fragmento --- 

                # Verificar si existen escalas (lógica de extracción de debug_data)
                cotizacion_id = datos_cotizacion.get('id')
                if cotizacion_id:
                    print(f"Buscando escalas de la cotización ID: {cotizacion_id}")
                    resultados_debug = []
                    try:
                        # Simular una búsqueda de datos que podría estar en los logs
                        if datos_cotizacion.get('debug_data'):
                            debug_data = datos_cotizacion.get('debug_data', '')
                            lines = debug_data.strip().split('\n')
                            busqueda_escalas = "Escala:"
                            for i, line in enumerate(lines):
                                if busqueda_escalas in line and "Valor unidad:" in line:
                                    parts = line.strip().split(',')
                                    if len(parts) >= 2:
                                        escala_str = parts[0].replace("Escala:", "").strip()
                                        valor_str = parts[1].replace("Valor unidad:", "").strip()
                                        try:
                                            escala = int(escala_str)
                                            valor_unidad = float(valor_str)
                                            resultados_debug.append({
                                                "escala": escala,
                                                "valor_unidad": valor_unidad
                                            })
                                            print(f"Extraído de logs: Escala {escala}, Valor {valor_unidad}")
                                        except (ValueError, TypeError):
                                            print(f"Error al convertir valores: {escala_str}, {valor_str}")
                        if resultados_debug:
                            print(f"Se encontraron {len(resultados_debug)} escalas en los logs de depuración. Usándolas.")
                            datos_cotizacion['resultados'] = resultados_debug
                    except Exception as e:
                        print(f"Error al procesar datos de depuración: {str(e)}")

                # Asegurarse de que exista la clave 'resultados'
                if 'resultados' not in datos_cotizacion or not datos_cotizacion['resultados']:
                    print("AVISO: No se encontraron resultados en los datos. Usando valores predeterminados.")
                    datos_cotizacion['resultados'] = self._crear_resultados_predeterminados()

                # Preparar el logo
                try:
                    # Asegúrate que la ruta 'assests/logo_flexoimpresos.png' sea correcta desde donde se ejecuta el script
                    logo = Image("assests/logo_flexoimpresos.png") 
                    logo.drawWidth = 1.2 * inch  # Reducido aún más (de 1.5 a 1.2 inch)
                    logo.drawHeight = (501/422) * logo.drawWidth 
                except Exception as e:
                    print(f"Error al cargar el logo: {str(e)}")
                    logo = EmptyImage(1.2*inch, (501/422)*1.2*inch)  # También ajustado aquí

                # Obtener el consecutivo (numero_cotizacion) de forma segura
                consecutivo = 0
                try:
                    num_cotizacion = datos_cotizacion.get("consecutivo")
                    if num_cotizacion is not None:
                        consecutivo = int(num_cotizacion)
                    else:
                        print("ADVERTENCIA: No se encontró 'consecutivo' (numero_cotizacion). Usando 0.")
                except (ValueError, TypeError):
                    print(f"Error al convertir consecutivo: {datos_cotizacion.get('consecutivo')}. Usando 0.")

                # Encabezado
                header_data = [
                    [logo, 'FLEXO IMPRESOS S.A.S.', ''],
                    ['', 'NIT: 900.528.680-0', ''],
                    ['', 'CALLE 28 A 65 A 9', 'COTIZACION'],
                    ['', 'MEDELLIN - ANTIOQUIA', f'CT{consecutivo:08d}']
                ]
                header_data.append(['', 'Tel: (604) 444-9661', ''])
                header_table = Table(header_data, colWidths=[1.6*inch, 3.4*inch, 1.5*inch])  # Ajustadas las proporciones
                
                idx_cotizacion = 2
                idx_consecutivo = 3
                header_styles = [
                    ('ALIGN', (0,0), (0,-1), 'CENTER'), 
                    ('ALIGN', (1,0), (1,-1), 'CENTER'), 
                    ('ALIGN', (2,0), (2,-1), 'RIGHT'),  
                    ('VALIGN', (0,0), (-1,-1), 'MIDDLE'), 
                    ('FONTNAME', (1,0), (1,-1), 'Helvetica-Bold'),
                    ('FONTSIZE', (1,0), (1,-1), 10),
                    ('SPAN', (0,0), (0,-1)), 
                    ('FONTNAME', (2,idx_cotizacion), (2,idx_consecutivo), 'Helvetica-Bold'),
                    ('FONTSIZE', (2,idx_cotizacion), (2,idx_consecutivo), 10),
                    ('LINEABOVE', (2,idx_cotizacion), (2,idx_cotizacion), 1, colors.black),
                    ('LINEBELOW', (2,idx_consecutivo), (2,idx_consecutivo), 1, colors.black),
                    ('LINEBEFORE', (2,idx_cotizacion), (2,idx_consecutivo), 1, colors.black),
                    ('LINEAFTER', (2,idx_cotizacion), (2,idx_consecutivo), 1, colors.black),
                    ('TOPPADDING', (2,idx_cotizacion), (2,idx_consecutivo), 4),  # Reducido de 6
                    ('BOTTOMPADDING', (2,idx_cotizacion), (2,idx_consecutivo), 4),  # Reducido de 6
                    ('RIGHTPADDING', (2,idx_cotizacion), (2,idx_consecutivo), 8),  # Reducido de 12
                    ('LEFTPADDING', (2,idx_cotizacion), (2,idx_consecutivo), 8),  # Reducido de 12
                    # Ajustar espaciado de las celdas del encabezado (interlineado sencillo)
                    ('TOPPADDING', (1,0), (1,-1), 1),  # Reducido al mínimo
                    ('BOTTOMPADDING', (1,0), (1,-1), 1),  # Reducido al mínimo
                ]
                header_table.setStyle(TableStyle(header_styles))
                elements.append(header_table)
                elements.append(Spacer(1, 10))  # Reducido aún más (de 15 a 10)

                # Fecha y cliente
                meses = {1: 'Enero', 2: 'Febrero', 3: 'Marzo', 4: 'Abril', 5: 'Mayo', 6: 'Junio', 
                         7: 'Julio', 8: 'Agosto', 9: 'Septiembre', 10: 'Octubre', 11: 'Noviembre', 12: 'Diciembre'}
                fecha_actual = datetime.now()
                fecha = f"{meses[fecha_actual.month]} {fecha_actual.day} de {fecha_actual.year}"
                
                elements.append(Paragraph(f"Medellín, {fecha}", self.styles['Normal']))
                elements.append(Spacer(1, 10))
                elements.append(Paragraph(f"Señores:", self.styles['Normal']))
                # Usar 'nombre_cliente' del diccionario de datos
                elements.append(Paragraph(datos_cotizacion.get('nombre_cliente', 'CLIENTE NO ESPECIFICADO'), self.styles['Normal']))
                elements.append(Spacer(1, 10))

                # Detalles del producto/referencia
                identificador = datos_cotizacion.get('identificador', '')
                # Formatear dimensiones sin redondeo para la referencia
                def _fmt_medida(value):
                    try:
                        # Usar exactamente la misma función que en report_generator.py
                        if value is None or value == "":
                            return "N/A"
                        d = Decimal(str(value))
                        s = format(d.normalize(), 'f')
                        if '.' in s:
                            s = s.rstrip('0').rstrip('.')
                        return s
                    except Exception:
                        return str(value)

                # Solución RADICAL para el formato del identificador
                identificador_original = datos_cotizacion.get('identificador', '')
                ancho = datos_cotizacion.get('ancho')
                avance = datos_cotizacion.get('avance')
                
                print(f"DEBUG PDF - VALORES ORIGINALES: identificador={identificador_original}, ancho={ancho}, avance={avance}")
                
                # Función ULTRA SIMPLIFICADA para formatear medidas
                def format_measure(value):
                    try:
                        if value is None or value == "":
                            return "N/A"
                        
                        # Convertir a float primero para asegurarnos que es un número
                        num = float(value)
                        
                        # Verificar si es un número entero
                        if num == int(num):
                            return str(int(num))
                        else:
                            # Si tiene decimales, formatear sin ceros a la derecha
                            return str(num).rstrip('0').rstrip('.') if '.' in str(num) else str(num)
                    except Exception as e:
                        print(f"Error en format_measure: {e}")
                        return str(value)
                
                # Formatear las dimensiones
                ancho_fmt = format_measure(ancho)
                avance_fmt = format_measure(avance)
                
                print(f"DEBUG PDF - DIMENSIONES FORMATEADAS: ancho_fmt={ancho_fmt}, avance_fmt={avance_fmt}")
                
                # SOLUCIÓN ULTRA RADICAL: Reconstruir el identificador completo
                if identificador_original and ancho_fmt != "N/A" and avance_fmt != "N/A":
                    # Dividir el identificador en partes
                    partes = identificador_original.upper().split()
                    print(f"DEBUG PDF - PARTES DEL IDENTIFICADOR: {partes}")
                    
                    # Buscar la parte que contiene las dimensiones exactamente
                    dimension_encontrada = False
                    for i, parte in enumerate(partes):
                        # Buscar patrón como "50.01X50.0MM" o "50X50MM" 
                        if ('X' in parte or 'x' in parte) and ('MM' in parte or 'mm' in parte.lower()):
                            try:
                                # Extraer las dimensiones actuales
                                parte_limpia = parte.upper().replace('MM', '')
                                dims_actuales = parte_limpia.split('X')
                                if len(dims_actuales) == 2:
                                    # Construir nueva dimensión con nuestros valores formateados
                                    dimensiones_nuevas = f"{ancho_fmt}X{avance_fmt}MM"
                                    print(f"DEBUG PDF - REEMPLAZANDO DIMENSIÓN: '{parte}' -> '{dimensiones_nuevas}'")
                                    partes[i] = dimensiones_nuevas
                                    dimension_encontrada = True
                                    break
                            except Exception as e:
                                print(f"Error al procesar parte '{parte}': {e}")
                    
                    if not dimension_encontrada:
                        print(f"ADVERTENCIA: No se encontró patrón de dimensiones en '{identificador_original}'")
                    
                    # Reconstruir el identificador
                    identificador_final = ' '.join(partes)
                    print(f"DEBUG PDF - IDENTIFICADOR FINAL: {identificador_final}")
                else:
                    identificador_final = identificador_original.upper() if identificador_original else ''
                    print(f"DEBUG PDF - NO SE PUDO FORMATEAR, USANDO ORIGINAL: {identificador_final}")
                
                # Mostrar el identificador en el PDF
                if identificador_original:
                    elements.append(Paragraph(f"Referencia: {identificador_final}", self.styles['Normal']))
                
                
                material_nombre = datos_cotizacion.get('material', {}).get('nombre', 'N/A')
                elements.append(Paragraph(f"Material: {material_nombre}", self.styles['Normal']))
                
                adhesivo = datos_cotizacion.get('adhesivo_tipo', 'No aplica')
                adhesivo_display = adhesivo.upper() if adhesivo != 'No aplica' else adhesivo
                
                es_manga = datos_cotizacion.get('es_manga')
                # Corregir cómo se obtiene acabado_id y tipo_foil_nombre
                acabado_data = datos_cotizacion.get('acabado', {}) # Obtener el diccionario de acabado
                acabado_id = acabado_data.get('id') # Obtener el ID desde el diccionario de acabado
                acabado_nombre_original = acabado_data.get('nombre', 'N/A') # Obtener el nombre desde el diccionario de acabado
                tipo_foil_nombre = datos_cotizacion.get('tipo_foil_nombre') # Este ya se obtiene directamente

                # DEBUG PDF GENERATOR
                print(f"--- DEBUG PDF gen (Revisado) ---")
                print(f"es_manga: {es_manga}")
                print(f"acabado_id (from acabado_data.get('id')): {acabado_id}")
                print(f"acabado_nombre_original (from acabado_data.get('nombre')): {acabado_nombre_original}")
                print(f"tipo_foil_nombre: {tipo_foil_nombre}")
                # --- FIN DEBUG ---

                if not es_manga:
                    elements.append(Paragraph(f"Adhesivo: {adhesivo_display}", self.styles['Normal']))
                    
                    # --- INICIO LÓGICA CORREGIDA PARA ACABADO ---
                    acabado_presente_y_valido = bool(acabado_data and acabado_id is not None)
                    
                    if acabado_presente_y_valido:
                        # Verificar si es el acabado a omitir explícitamente
                        omitir_sin_acabado = (acabado_nombre_original.upper() == 'SIN ACABADO')
                                              
                        if not omitir_sin_acabado:
                            # Acabado presente y no es "SIN ACABADO", mostrarlo
                            acabado_a_mostrar = acabado_nombre_original
                            # Modificar nombre si es FOIL
                            if acabado_id in [5, 6]: 
                                print(f"  Processing acabado FOIL. Original: '{acabado_nombre_original}', ID: {acabado_id}")
                                if "LAMINADO BRILLANTE + FOIL" in acabado_nombre_original.upper():
                                    acabado_a_mostrar = "LAMINADO BRILLANTE"
                                    print(f"    Set acabado_a_mostrar to: {acabado_a_mostrar}")
                                elif "LAMINADO MATE + FOIL" in acabado_nombre_original.upper():
                                    acabado_a_mostrar = "LAMINADO MATE"
                                    print(f"    Set acabado_a_mostrar to: {acabado_a_mostrar}")
                                else:
                                    print(f"    Acabado ID is {acabado_id} but original name '{acabado_nombre_original}' does not match expected FOIL patterns.")
                            elements.append(Paragraph(f"Acabado: {acabado_a_mostrar}", self.styles['Normal']))
                            print(f"  Displaying acabado: {acabado_a_mostrar}")
                        else:
                            # Es explícitamente "SIN ACABADO", no añadir línea
                            print(f"  Skipping acabado line because it is ID 10 or named 'SIN ACABADO'.")
                    else:
                        # No había datos válidos de acabado
                        print(f"  No valid acabado data found. Skipping acabado line.")
                    # --- FIN LÓGICA CORREGIDA PARA ACABADO ---
                
                num_tintas_original = datos_cotizacion.get('num_tintas', 0)
                if num_tintas_original > 0:
                    texto_tintas = f"Tintas: {num_tintas_original}"
                    print(f"  Processing tintas. num_tintas_original: {num_tintas_original}, es_manga: {es_manga}, acabado_id: {acabado_id}, tipo_foil_nombre: {tipo_foil_nombre}")
                    if not es_manga and acabado_id in [5, 6] and tipo_foil_nombre:
                        texto_tintas = f"Tintas: {num_tintas_original} + COLD FOIL {tipo_foil_nombre.upper()}"
                        print(f"    Set texto_tintas to: {texto_tintas}")
                    elements.append(Paragraph(texto_tintas, self.styles['Normal']))
                else:
                    print(f"  Skipping tintas line as num_tintas_original is 0.")
                print(f"--- END DEBUG PDF gen (Revisado) ---")
                
                num_rollos = datos_cotizacion.get('num_rollos', 0)
                # Formatear con punto como separador de miles 
                rollos_texto = f"{num_rollos:,}".replace(',', '.')
                if es_manga:
                    elements.append(Paragraph(f"MT X PAQUETE: {rollos_texto}", self.styles['Normal']))
                else:
                    elements.append(Paragraph(f"ET X ROLLO: {rollos_texto}", self.styles['Normal']))
                
                if es_manga and datos_cotizacion.get('tipo_grafado'):
                    tipo_grafado = datos_cotizacion['tipo_grafado']
                    if tipo_grafado is not None:
                        if isinstance(tipo_grafado, int):
                            grafado_textos = {1: "Sin grafado", 2: "Vertical Total", 3: "Horizontal Total", 4: "Horizontal Total + Vertical"}
                            tipo_grafado_texto = grafado_textos.get(tipo_grafado, f"Tipo {tipo_grafado}")
                            # Convertir a mayúsculas
                            tipo_grafado_texto = tipo_grafado_texto.upper()
                        else:
                            tipo_grafado_texto = str(tipo_grafado).upper() # Convertir a mayúsculas
                        
                        # Verificar si existe altura de grafado y añadirla al texto
                        altura_grafado = datos_cotizacion.get('altura_grafado')
                        print(f"\n=== DEBUG ALTURA GRAFADO ===")
                        print(f"Tipo grafado: {tipo_grafado} (tipo: {type(tipo_grafado)})")
                        print(f"Altura grafado: {altura_grafado} (tipo: {type(altura_grafado)})")
                        print(f"Condición cumplida: {altura_grafado is not None and tipo_grafado in [3, 4]}")
                        
                        # Asegurar que altura_grafado sea un número formateado correctamente
                        if altura_grafado is not None:
                            try:
                                from decimal import Decimal
                                d = Decimal(str(altura_grafado))
                                altura_grafado_fmt = format(d.normalize(), 'f')
                                if '.' in altura_grafado_fmt:
                                    altura_grafado_fmt = altura_grafado_fmt.rstrip('0').rstrip('.')
                                print(f"Altura formateada (sin redondeo): {altura_grafado_fmt}")
                            except (ValueError, TypeError):
                                altura_grafado_fmt = str(altura_grafado)
                                print(f"Error al formatear altura, usando como string: {altura_grafado_fmt}")
                        else:
                            altura_grafado_fmt = "0"
                            print("Altura no encontrada, usando valor por defecto")
                        
                        if altura_grafado is not None and tipo_grafado in [3, 4]:  # Solo mostrar altura para grafado horizontal (3) y horizontal+vertical (4)
                            texto_grafado = f"Grafado: {tipo_grafado_texto} A {altura_grafado_fmt} MM"
                            print(f"Texto del grafado final: {texto_grafado}")
                            elements.append(Paragraph(texto_grafado, self.styles['Normal']))
                        else:
                            elements.append(Paragraph(f"Grafado: {tipo_grafado_texto}", self.styles['Normal']))
                    else:
                        elements.append(Paragraph(f"Grafado: No especificado", self.styles['Normal']))
                
                # --- MODIFICACIÓN INICIO: Condición más robusta para mostrar costo de preprensa ---
                # Se verifica explícitamente si las planchas se deben cobrar por separado
                # y si el valor de preprensa es positivo.
                planchas_son_separadas = datos_cotizacion.get('planchas_x_separado', False)
                valor_plancha_separado = datos_cotizacion.get('valor_plancha_separado')

                print(f"\n=== DEBUG COSTO PREPRENSA ===")
                print(f"planchas_son_separadas: {planchas_son_separadas}")
                print(f"valor_plancha_separado (tipo): {type(valor_plancha_separado)}")
                print(f"valor_plancha_separado (valor): {valor_plancha_separado}")

                if planchas_son_separadas and valor_plancha_separado is not None:
                    try:
                        # Si es Decimal, convertir a float
                        if isinstance(valor_plancha_separado, Decimal):
                            valor_plancha_float = float(valor_plancha_separado)
                        else:
                            valor_plancha_float = float(valor_plancha_separado)
                            
                        if valor_plancha_float > 0:
                            elements.append(Paragraph(f"Costo Preprensa: ${valor_plancha_float:,.0f}", self.styles['Normal']))
                            print(f"DEBUG PDF: Mostrando costo preprensa: ${valor_plancha_float:,.0f}")
                    except (ValueError, TypeError) as e:
                        print(f"Error al procesar valor_plancha_separado: {e}")
                else:
                    print(f"DEBUG PDF: No se muestra costo preprensa - planchas_son_separadas: {planchas_son_separadas}, valor_plancha_separado: {valor_plancha_separado}")
                # --- MODIFICACIÓN FIN ---
                
                elements.append(Spacer(1, 20))

                # Tabla de resultados (escalas)
                print("\n=== DEBUG TABLA DE RESULTADOS (Adaptado) ===")
                print(f"Resultados a procesar: {datos_cotizacion.get('resultados')}")
                table_data = [["Escala", "Valor Unidad"]] 
                try:
                    resultados = datos_cotizacion.get('resultados', [])
                    if not isinstance(resultados, list):
                        print("Advertencia: 'resultados' no es una lista, intentando convertir.")
                        resultados = [resultados] # Intentar convertir a lista
                        
                    if not resultados: # Verificar si está vacía después de la conversión
                         print("Error: La lista 'resultados' está vacía.")
                         # Podrías añadir una fila de error o usar los predeterminados de nuevo
                         resultados = self._crear_resultados_predeterminados()

                    for r in resultados:
                        if not isinstance(r, dict):
                            print(f"Advertencia: Elemento en resultados no es un diccionario: {r}. Saltando.")
                            continue
                        try:
                            escala = r.get('escala', 0)
                            valor_unidad = r.get('valor_unidad', 0.0)
                            
                            # Conversión robusta
                            try:
                                # Primero limpiar cualquier formato de la escala (comas, etc.)
                                if isinstance(escala, str):
                                    escala_limpia = escala.replace(',', '').replace('$', '').strip()
                                else:
                                    escala_limpia = str(escala)
                                
                                # Convertir a float primero para manejar decimales
                                escala_float = float(escala_limpia)
                                
                                # Aplicar redondeo hacia arriba (ceiling) y convertir a entero
                                escala_val = int(math.ceil(escala_float))
                                print(f"Escala procesada: {escala} -> {escala_float} -> {escala_val}")
                            except (ValueError, TypeError) as e:
                                escala_val = 0
                                print(f"Error convirtiendo escala: {escala}, Error: {str(e)}")
                                
                            try:
                                valor_unidad_val = float(str(valor_unidad).replace('$', '').replace(',', ''))
                                # Aplicar redondeo hacia arriba al valor de la unidad y convertir a entero
                                valor_unidad_val = int(math.ceil(valor_unidad_val))
                                print(f"Valor unidad redondeado: {valor_unidad} -> {valor_unidad_val}")
                            except (ValueError, TypeError):
                                valor_unidad_val = 0
                                print(f"Error convirtiendo valor_unidad: {valor_unidad}")
                                
                            # Formateo con puntos para miles (cambiando comas por puntos)
                            escala_fmt = f"{escala_val:,}".replace(',', '.')
                            # Para valor_unidad: ahora es entero, sin decimales (con punto como separador de miles)
                            valor_unidad_fmt = f"${valor_unidad_val:,}".replace(',', '.') # Sin .2f para mantener entero
                            
                            print(f"Añadiendo fila: [{escala_fmt}, {valor_unidad_fmt}]")
                            table_data.append([escala_fmt, valor_unidad_fmt])
                        except Exception as e_inner:
                            print(f"Error procesando resultado individual: {str(e_inner)}, {r}")
                            traceback.print_exc()
                            table_data.append(["Error", "Error"])

                    print(f"Tabla de datos final: {table_data}")
                    if len(table_data) > 1:
                        tabla = Table(table_data, colWidths=[170, 170])
                        style = TableStyle([
                            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
                            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                            ('FONTSIZE', (0, 0), (-1, 0), 11),
                            ('TOPPADDING', (0, 0), (-1, 0), 4),
                            ('BOTTOMPADDING', (0, 0), (-1, 0), 4),
                            ('BACKGROUND', (0, 1), (-1, -1), colors.white),
                            ('GRID', (0, 0), (-1, -1), 1, colors.black),
                            ('ALIGN', (0, 1), (0, -1), 'CENTER'),
                            ('ALIGN', (1, 1), (1, -1), 'RIGHT'),
                            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                            ('FONTSIZE', (0, 1), (-1, -1), 9),
                            ('TOPPADDING', (0, 1), (-1, -1), 3),
                            ('BOTTOMPADDING', (0, 1), (-1, -1), 3),
                        ])
                        tabla.setStyle(style)
                        elements.append(tabla)
                        print("Tabla agregada exitosamente")
                        elements.append(Spacer(1, 20))
                except Exception as e_table:
                    print(f"Error fatal procesando tabla de resultados: {str(e_table)}")
                    traceback.print_exc()
                    elements.append(Paragraph("Error al generar la tabla de precios.", self.styles['Normal']))
                    elements.append(Spacer(1, 20))

                # Políticas y condiciones
                elements.append(Paragraph("I.V.A (no incluido): 19%", self.styles['Normal']))
                elements.append(Paragraph("% de Tolerancia: 10% + ó - de acuerdo a la cantidad pedida", self.styles['Normal']))
                elements.append(Spacer(1, 3))

                elements.append(Paragraph("Política de Entrega:", self.styles['Heading2']))
                
                # Verificar si hay una política específica en los datos
                politica_entrega = datos_cotizacion.get('politica_entrega')
                
                if politica_entrega and politica_entrega != "Estándar":
                    # --- INICIO MODIFICACIÓN: Procesar saltos de línea en política de entrega ---
                    # Dividir el texto por saltos de línea y crear un párrafo para cada línea
                    lineas_politica = politica_entrega.split("\n")
                    for linea in lineas_politica:
                        if linea.strip():  # Asegurarse de que la línea no esté vacía
                            elements.append(Paragraph(f"• {linea.strip()}", self.styles['Normal']))
                    # --- FIN MODIFICACIÓN ---
                else:
                    # Usar las políticas estáticas predeterminadas
                    elements.append(Paragraph("• Repeticiones: 13 días calendario a partir de la confirmación del pedido", self.styles['Normal']))
                    elements.append(Paragraph("• Cambios: 15 días calendario a partir de la aprobación del sherpa", self.styles['Normal']))
                    elements.append(Paragraph("• Nuevos: 20 días calendario a partir de la aprobación del sherpa", self.styles['Normal']))
                
                elements.append(Spacer(1, 2))
                elements.append(Paragraph("Política de Cartera:", self.styles['Heading2']))
                
                # DEBUG: Imprimir todos los datos para ver qué tenemos
                print("\n=== DEBUG POLÍTICA DE CARTERA EN PDF ===")
                print(f"Tipo de datos_cotizacion: {type(datos_cotizacion)}")
                print(f"Claves en datos_cotizacion: {list(datos_cotizacion.keys())}")
                
                # Obtener la política de cartera de los datos (similar a política de entrega)
                politica_cartera = datos_cotizacion.get('politica_cartera')
                print(f"Política de cartera obtenida: {politica_cartera}")
                print(f"Tipo de política de cartera: {type(politica_cartera)}")
                
                # Usar la política de cartera
                if politica_cartera and isinstance(politica_cartera, str):
                    print(f"Usando política de cartera: {politica_cartera}")
                    try:
                        # Dividir el texto por líneas y agregar cada una como un punto
                        lineas_politica = politica_cartera.split('\n')
                        for linea in lineas_politica:
                            if linea.strip():
                                elements.append(Paragraph(f"• {linea.strip()}", self.styles['Normal']))
                                print(f"Agregada línea: • {linea.strip()}")
                    except Exception as e:
                        print(f"Error al procesar política de cartera: {str(e)}")
                        # En caso de error, usar valores hardcodeados como último recurso
                        elements.append(Paragraph("• Se retiene despacho con mora de 16 a 30 días", self.styles['Normal']))
                        elements.append(Paragraph("• Se retiene producción con mora de 31 a 45 días", self.styles['Normal']))
                else:
                    print("No se encontró política de cartera válida, usando valores hardcodeados")
                    # Políticas hardcodeadas como último recurso
                    elements.append(Paragraph("• Se retiene despacho con mora de 16 a 30 días", self.styles['Normal']))
                    elements.append(Paragraph("• Se retiene producción con mora de 31 a 45 días", self.styles['Normal']))
                
                print("=== FIN DEBUG POLÍTICA DE CARTERA ===\n")
                elements.append(Spacer(1, 10))
                elements.append(Paragraph("Vigencia de la cotización: 30 días", self.styles['Normal']))
                
                # Firma del comercial
                elements.append(Spacer(1, 20))
                elements.append(HRFlowable(width="100%", thickness=1, lineCap='round', color=colors.HexColor('#CCCCCC')))
                elements.append(Spacer(1, 10))
                
                if datos_cotizacion.get('comercial'):
                    comercial = datos_cotizacion['comercial']
                    nombre_comercial = comercial.get('nombre')
                    if nombre_comercial:
                        elements.append(Paragraph(nombre_comercial.upper(), self.firma_style))
                    else:
                        elements.append(Paragraph("COMERCIAL NO ESPECIFICADO", self.firma_style))
                    
                    if comercial.get('email'):
                        elements.append(Paragraph(f"Email: {comercial['email']}", self.firma_style))
                    if comercial.get('celular'):
                        elements.append(Paragraph(f"Cel: {comercial['celular']}", self.firma_style))
                    print("\n=== DEBUG DATOS COMERCIAL EN PDF (Adaptado) ===")
                    print(f"Nombre: {comercial.get('nombre')}, Email: {comercial.get('email')}, Cel: {comercial.get('celular')}")
                else:
                    print("Advertencia: No se encontraron datos del comercial.")
                    elements.append(Paragraph("Atentamente,", self.firma_style))

                # --- Fin del código adaptado --- 

                # Construir el PDF en el archivo temporal
                doc.build(elements)
                print(f"PDF generado temporalmente en: {tmp_file.name}")

            # Leer los bytes del archivo temporal
            with open(tmp_file.name, "rb") as f:
                pdf_bytes = f.read()
            print(f"Bytes del PDF leídos: {len(pdf_bytes)}")
            return pdf_bytes

        except Exception as e:
            print(f"Error fatal durante la generación de PDF en CotizacionPDF (Adaptado): {e}")
            traceback.print_exc()
            return None
        finally:
            # Eliminar el archivo temporal
            if tmp_file and os.path.exists(tmp_file.name):
                try:
                    os.remove(tmp_file.name)
                    print(f"Archivo temporal eliminado: {tmp_file.name}")
                except Exception as e_del:
                    print(f"Error eliminando archivo temporal {tmp_file.name}: {e_del}")

    def _generar_seccion_cliente(self, cliente: Dict[str, Any]) -> List:
        """Genera la sección de información del cliente (NO USADO en la estructura actual)"""
        elements = [Paragraph("<b>Información del Cliente:</b>", self.styles['Normal']), Spacer(1, 10)]
        
        data = [
            ["Nombre:", cliente.get('nombre', 'N/A')],
            ["NIT:", cliente.get('nit', 'N/A')],
            ["Dirección:", cliente.get('direccion', 'N/A')],
            ["Teléfono:", cliente.get('telefono', 'N/A')],
            ["Email:", cliente.get('email', 'N/A')]
        ]
        
        table = Table(data, colWidths=[100, 300])
        table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('GRID', (0,0), (-1,-1), 0.5, colors.grey), # Opcional: añadir rejilla
            # ('SPAN', (1, 0), (1, 0)) # Ejemplo si quieres que una celda ocupe más
        ]))
        elements.append(table)
        elements.append(Spacer(1, 20)) # Espacio después de la sección
        return elements

    def _generar_seccion_producto(self, cotizacion: Dict[str, Any]) -> List:
        """Genera la sección de detalles del producto/referencia (NO USADO en la estructura actual)"""
        elements = [Paragraph("<b>Detalles del Producto:</b>", self.styles['Normal']), Spacer(1, 10)]
        ref_cliente = cotizacion.get('referencia_cliente', {})
        
        # Helper para formatear números o devolver N/A
        def format_value(value, format_spec=".2f"):
            if isinstance(value, (int, float)):
                try:
                    return f"{value:{format_spec}}"
                except (ValueError, TypeError):
                    return str(value) # Si el formato falla por alguna razón
            return str(value) # Devuelve como string si no es numérico o es N/A

        ancho = ref_cliente.get('ancho', 'N/A')
        largo = ref_cliente.get('largo', 'N/A')
        gap = ref_cliente.get('gap', 'N/A')
        tintas = ref_cliente.get('numero_tintas', 'N/A')

        data = [
            ["Referencia:", ref_cliente.get('nombre', 'N/A')],
            ["Código:", ref_cliente.get('codigo', 'N/A')],
            # ["Descripción:", ref_cliente.get('descripcion_material', 'N/A')], 
            ["Ancho (mm):", format_value(ancho)],
            ["Largo (mm):", format_value(largo)],
            ["Gap (mm):", format_value(gap)],
            ["Tintas:", format_value(tintas, "")] # Sin formato decimal para tintas
        ]

        # Si hay observaciones, añadirlas
        observaciones = ref_cliente.get('observaciones')
        if observaciones:
            # Usamos un párrafo para permitir texto más largo y con formato
            obs_paragraph = Paragraph(f"<b>Observaciones:</b><br/>{observaciones}", self.styles['Normal'])
            data.append([obs_paragraph, ""]) # Ocupa ambas columnas

            table = Table(data, colWidths=[100, 300])
            table.setStyle(TableStyle([
                ('ALIGN', (0, 0), (-1, -2), 'LEFT'), # Estilo para todas menos la última fila
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('FONTNAME', (0, 0), (0, -2), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -2), 10),
                ('BOTTOMPADDING', (0, 0), (-1, -2), 3),
                ('TOPPADDING', (0, 0), (-1, -2), 3),
                ('GRID', (0,0), (-1,-2), 0.5, colors.grey),
                # Estilo para la fila de observaciones
                ('SPAN', (0, -1), (1, -1)), # Unir celdas para observaciones
                ('ALIGN', (0, -1), (0, -1), 'LEFT'),
                ('VALIGN', (0, -1), (0, -1), 'TOP'),
                ('BOTTOMPADDING', (0, -1), (0, -1), 5),
                ('TOPPADDING', (0, -1), (0, -1), 5),
            ]))
        else:
            # Tabla sin la fila de observaciones
            table = Table(data, colWidths=[100, 300])
            table.setStyle(TableStyle([
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
                ('TOPPADDING', (0, 0), (-1, -1), 3),
                ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
            ]))

        elements.append(table)
        elements.append(Spacer(1, 20))
        return elements

    def _generar_tabla_escalas(self, escalas: List[Dict[str, Any]]) -> List:
        """Genera la tabla de escalas de producción (NO USADO en la estructura actual)"""
        elements = [Paragraph("<b>Escalas de Precios:</b>", self.styles['Normal']), Spacer(1, 10)]
        
        # Encabezados de la tabla
        data = [["Cantidad", "Precio Unitario", "Precio Total"]]
        
        # Añadir filas de datos desde las escalas
        for escala in escalas:
            cantidad = escala.get('cantidad', 0)
            precio_unitario = escala.get('precio_unitario', 0.0)
            precio_total = escala.get('precio_total', 0.0)
            
            # Formatear como moneda (ej. $ 1,234.56)
            # Asumiendo que quieres formato COP, puedes ajustar locale o usar f-string
            # Para simplicidad, usaremos f-string con comas y 2 decimales
            formatted_unitario = f"$ {precio_unitario:,.2f}"
            formatted_total = f"$ {precio_total:,.2f}"
            
            data.append([f"{cantidad:,}", formatted_unitario, formatted_total])
            
        table = Table(data, colWidths=[100, 150, 150])
        # Aplicar el estilo base y personalizar si es necesario
        style = TableStyle(self.config.table_style)
        # Podrías añadir estilos específicos aquí si es necesario
        # Ejemplo: Alinear precios a la derecha
        style.add('ALIGN', (1, 1), (-1, -1), 'RIGHT') 
        table.setStyle(style)
        
        elements.append(table)
        elements.append(Spacer(1, 20))
        return elements

    def _generar_seccion_tecnica(self, cotizacion: Dict[str, Any]) -> List:
        """Genera la sección de información técnica (NO USADO en la estructura actual)"""
        elements = [Paragraph("<b>Información Técnica:</b>", self.styles['Normal']), Spacer(1, 10)]
        
        data = [
            ["Material Solicitado:", cotizacion.get('material_solicitado', 'N/A')],
            ["Tipo Adhesivo:", cotizacion.get('tipo_adhesivo', 'N/A')],
            ["Acabado:", cotizacion.get('acabado', 'N/A')],
            ["Sentido Salida Rollo:", cotizacion.get('sentido_salida_rollo', 'N/A')],
            ["Diámetro Core (pulgadas):", cotizacion.get('diametro_core', 'N/A')]
            # Añadir más campos técnicos según sea necesario
        ]
        
        table = Table(data, colWidths=[150, 250]) # Ajustar anchos según necesidad
        table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
        ]))
        
        elements.append(table)
        elements.append(Spacer(1, 20))
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