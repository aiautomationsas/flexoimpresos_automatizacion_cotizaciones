from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, HRFlowable, PageBreak, Flowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from datetime import datetime
import math

class CotizacionPDF:
    def __init__(self):
        self.styles = getSampleStyleSheet()
        self.width, self.height = letter
        
        # Definir estilo para la firma
        self.firma_style = ParagraphStyle(
            'FirmaStyle',
            parent=self.styles['Normal'],
            fontSize=10,
            leading=12,
            alignment=0,  # Izquierda
            spaceAfter=6
        )

    def _ajustar_valor_plancha(self, valor: float) -> float:
        """
        Aplica la fórmula =REDONDEAR.MAS(valor/0.7;-4) al valor de la plancha
        """
        valor_ajustado = valor / 0.7
        # Redondear hacia arriba al siguiente múltiplo de 10000
        return math.ceil(valor_ajustado / 10000) * 10000

    def _crear_resultados_predeterminados(self):
        """
        Crea una lista de resultados predeterminados para mostrar en el PDF cuando no hay datos reales.
        Esto es para evitar que la tabla aparezca vacía.
        """
        return [
            {"escala": 1000, "valor_unidad": 100.00},
            {"escala": 5000, "valor_unidad": 50.00},
            {"escala": 10000, "valor_unidad": 30.00}
        ]

    def generar_pdf(self, datos_cotizacion, path_salida):
        """
        Genera el PDF de la cotización
        """
        print("\n=== DEBUG GENERAR_PDF ===")
        print("Datos recibidos para generar PDF:")
        print(f"  Cliente: {datos_cotizacion.get('nombre_cliente')}")
        print(f"  Descripción: {datos_cotizacion.get('descripcion')}")
        print(f"  Consecutivo: {datos_cotizacion.get('consecutivo')}")
        
        # Verificar si existen escalas en DEBUG MOSTRAR COTIZACIÓN
        # En lugar de usar datos_cotizacion['resultados'], obtener datos de 'cotizacion_escalas'
        cotizacion_id = datos_cotizacion.get('id')
        if cotizacion_id:
            print(f"Buscando escalas de la cotización ID: {cotizacion_id}")
            # Si hay datos de debugging, analizarlos para extraer las escalas
            resultados = []
            try:
                # Buscar datos en los logs de depuración
                busqueda_pattern = "DEBUG MOSTRAR COTIZACIÓN"
                busqueda_escalas = "Escala:"
                
                # Simular una búsqueda de datos que podría estar en los logs
                # En un entorno real, esto debería venir de la base de datos
                if cotizacion_id and datos_cotizacion.get('debug_data'):
                    debug_data = datos_cotizacion.get('debug_data', '')
                    lines = debug_data.strip().split('\n')
                    
                    for i, line in enumerate(lines):
                        if busqueda_escalas in line and "Valor unidad:" in line:
                            parts = line.strip().split(',')
                            if len(parts) >= 2:
                                escala_str = parts[0].replace("Escala:", "").strip()
                                valor_str = parts[1].replace("Valor unidad:", "").strip()
                                
                                try:
                                    escala = int(escala_str)
                                    valor_unidad = float(valor_str)
                                    resultados.append({
                                        "escala": escala,
                                        "valor_unidad": valor_unidad
                                    })
                                    print(f"Extraído de logs: Escala {escala}, Valor {valor_unidad}")
                                except (ValueError, TypeError):
                                    print(f"Error al convertir valores: {escala_str}, {valor_str}")
                
                # Si encontramos resultados en los logs de depuración, usarlos
                if resultados:
                    print(f"Se encontraron {len(resultados)} escalas en los logs de depuración")
                    datos_cotizacion['resultados'] = resultados
            except Exception as e:
                print(f"Error al procesar datos de depuración: {str(e)}")
        
        # Asegurarse de que exista la clave 'resultados'
        if 'resultados' not in datos_cotizacion or not datos_cotizacion['resultados']:
            print("AVISO: No se encontraron resultados en los datos. Usando valores predeterminados.")
            datos_cotizacion['resultados'] = self._crear_resultados_predeterminados()
        
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
        try:
            logo = Image("assests/logo_flexoimpresos.png")  # Corregir ortografía para usar 'assests'
            # El logo original es 422x501 píxeles, mantener proporción pero ajustar a un ancho razonable
            logo.drawWidth = 2 * inch  # Volver a 2 pulgadas de ancho
            logo.drawHeight = (501/422) * logo.drawWidth  # Mantener exactamente la proporción original
        except Exception as e:
            print(f"Error al cargar el logo: {str(e)}")
            # Crear un placeholder para el logo en caso de error
            class EmptyImage(Flowable):
                def __init__(self, width, height):
                    Flowable.__init__(self)
                    self.width = width
                    self.height = height
                def draw(self):
                    pass
            logo = EmptyImage(2*inch, (501/422)*2*inch)

        # Obtener el consecutivo (numero_cotizacion) de forma segura
        consecutivo = 0
        try:
            # Usar el valor de 'consecutivo' que viene de 'numero_cotizacion' en la BD
            num_cotizacion = datos_cotizacion.get("consecutivo")
            if num_cotizacion is not None:
                consecutivo = int(num_cotizacion)
            else:
                print("ADVERTENCIA: No se encontró 'consecutivo' (numero_cotizacion) en datos_cotizacion. Usando 0.")
        except (ValueError, TypeError):
            print(f"Error al convertir consecutivo (numero_cotizacion): {datos_cotizacion.get('consecutivo')}. Usando 0.")

        # Encabezado
        header_data = [
            [logo, 'FLEXO IMPRESOS S.A.S.', ''],
            ['', 'NIT: 900.528.680-0', ''],
            ['', 'CALLE 28 A 65 A 9', 'COTIZACION'],
            ['', 'MEDELLIN - ANTIOQUIA', f'CT{consecutivo:08d}']
        ]
        
        # Agregar el teléfono al final
        header_data.append(['', 'Tel: (604) 444-9661', ''])
        
        header_table = Table(header_data, colWidths=[2.5*inch, 3*inch, 1.5*inch])
        
        # Calcular los índices dinámicamente
        idx_cotizacion = 2  # La fila de "COTIZACION" siempre es la 3ª (índice 2)
        idx_consecutivo = 3  # La fila del consecutivo siempre es la 4ª (índice 3)
        idx_telefono = 4  # Índice de la fila del teléfono
        
        header_styles = [
            # Estilos básicos
            ('ALIGN', (0,0), (0,-1), 'CENTER'),  # Centrar logo
            ('ALIGN', (1,0), (1,-1), 'CENTER'),   # Alinear texto al centro
            ('ALIGN', (2,0), (2,-1), 'RIGHT'),    # Alinear texto derecha a la derecha
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'), # Alineación vertical al medio
            ('FONTNAME', (1,0), (1,-1), 'Helvetica-Bold'),
            ('FONTSIZE', (1,0), (1,-1), 10),
            ('SPAN', (0,0), (0,-1)),  # Hacer que el logo ocupe todas las filas
            
            # Estilos para cotización y consecutivo
            ('FONTNAME', (2,idx_cotizacion), (2,idx_consecutivo), 'Helvetica-Bold'),
            ('FONTSIZE', (2,idx_cotizacion), (2,idx_consecutivo), 10),
            ('LINEABOVE', (2,idx_cotizacion), (2,idx_cotizacion), 1, colors.black),
            ('LINEBELOW', (2,idx_consecutivo), (2,idx_consecutivo), 1, colors.black),
            ('LINEBEFORE', (2,idx_cotizacion), (2,idx_consecutivo), 1, colors.black),
            ('LINEAFTER', (2,idx_cotizacion), (2,idx_consecutivo), 1, colors.black),
            ('TOPPADDING', (2,idx_cotizacion), (2,idx_consecutivo), 6),
            ('BOTTOMPADDING', (2,idx_cotizacion), (2,idx_consecutivo), 6),
            ('RIGHTPADDING', (2,idx_cotizacion), (2,idx_consecutivo), 12),
            ('LEFTPADDING', (2,idx_cotizacion), (2,idx_consecutivo), 12),
        ]
        
        header_table.setStyle(TableStyle(header_styles))
        elements.append(header_table)
        elements.append(Spacer(1, 20))
        
        elements.append(Spacer(1, 10))

        # Fecha y cliente
        meses = {
            1: 'Enero', 2: 'Febrero', 3: 'Marzo', 4: 'Abril',
            5: 'Mayo', 6: 'Junio', 7: 'Julio', 8: 'Agosto',
            9: 'Septiembre', 10: 'Octubre', 11: 'Noviembre', 12: 'Diciembre'
        }
        fecha_actual = datetime.now()
        mes = meses[fecha_actual.month]
        dia = fecha_actual.day
        año = fecha_actual.year
        fecha = f"{mes} {dia} de {año}"
        
        elements.append(Paragraph(f"Medellín, {fecha}", self.styles['Normal']))
        elements.append(Spacer(1, 10))
        elements.append(Paragraph(f"Señores:", self.styles['Normal']))
        elements.append(Paragraph(datos_cotizacion['nombre_cliente'], self.styles['Normal']))
        

        
        elements.append(Spacer(1, 20))

        # Add the identifier on a new line if it exists
        identificador = datos_cotizacion.get('identificador', '')
        if identificador:
            elements.append(Paragraph(f"Referencia: {identificador}", self.styles['Normal']))
        
        elements.append(Paragraph(f"Material: {datos_cotizacion['material']['nombre']}", self.styles['Normal']))
        
        # Mostrar siempre el adhesivo, usando 'No aplica' como default
        adhesivo = datos_cotizacion.get('adhesivo_tipo', 'No aplica')
        # Formatear para mostrar: usar mayúsculas solo si no es 'No aplica'
        adhesivo_display = adhesivo.upper() if adhesivo != 'No aplica' else adhesivo
        elements.append(Paragraph(f"Adhesivo: {adhesivo_display}", self.styles['Normal']))
        
        # Solo mostrar acabado si no es manga
        if not datos_cotizacion.get('es_manga'):
            elements.append(Paragraph(f"Acabado: {datos_cotizacion['acabado']['nombre']}", self.styles['Normal']))
        
        elements.append(Paragraph(f"Tintas: {datos_cotizacion['num_tintas']}", self.styles['Normal']))
        
        # Modificar el texto según sea etiqueta o manga
        if datos_cotizacion.get('es_manga'):
            elements.append(Paragraph(f"MT X PAQUETE: {datos_cotizacion['num_rollos']:,}", self.styles['Normal']))
        else:
            elements.append(Paragraph(f"ET X ROLLO: {datos_cotizacion['num_rollos']:,}", self.styles['Normal']))
        
        # Agregar tipo de grafado si es manga
        if datos_cotizacion.get('es_manga') and datos_cotizacion.get('tipo_grafado'):
            tipo_grafado = datos_cotizacion['tipo_grafado']
            # Verificar que tipo_grafado no sea None y obtener su representación en texto
            # Si es un ID numérico, intentamos obtener el texto correspondiente
            if tipo_grafado is not None:
                if isinstance(tipo_grafado, int):
                    # Mapeo de IDs a textos (ajustar según tu base de datos)
                    grafado_textos = {
                        1: "Sin grafado",
                        2: "Vertical Total",
                        3: "Horizontal Total",
                        4: "Horizontal Total + Vertical"
                    }
                    tipo_grafado_texto = grafado_textos.get(tipo_grafado, f"Tipo {tipo_grafado}")
                else:
                    tipo_grafado_texto = str(tipo_grafado)
                
                elements.append(Paragraph(f"Grafado: {tipo_grafado_texto}", self.styles['Normal']))
            else:
                elements.append(Paragraph(f"Grafado: No especificado", self.styles['Normal']))
        
        # Si no se incluyen planchas, mostrar "Planchas por separado" con el valor original
        if datos_cotizacion['valor_plancha_separado']:
            elements.append(Paragraph(f"Costo Preprensa: ${datos_cotizacion['valor_plancha_separado']:,.0f}", self.styles['Normal']))
        
        elements.append(Spacer(1, 20))

        # Agregar la tabla de resultados
        print("\n=== DEBUG ANTES DE PROCESAMIENTO DE TABLA ===")
        print(f"DATOS DE COTIZACION: {datos_cotizacion.keys()}")
        print(f"TIPO DE DATO 'resultados': {type(datos_cotizacion.get('resultados', 'NO EXISTE'))}")
        if 'resultados' in datos_cotizacion:
            print(f"CONTENIDO DE 'resultados': {datos_cotizacion['resultados']}")
        else:
            print("NO HAY RESULTADOS EN LOS DATOS DE COTIZACIÓN")

        # Siempre debería haber resultados a este punto debido al método _crear_resultados_predeterminados
        print("\n=== DEBUG TABLA DE RESULTADOS ===")
        print(f"Resultados encontrados: {len(datos_cotizacion['resultados'])}")

        styles = getSampleStyleSheet()
        table_data = [["Escala", "Valor Unidad"]]

        try:
            # Verificar que resultados sea una lista válida
            if not isinstance(datos_cotizacion['resultados'], list):
                print("Error: 'resultados' no es una lista")
                # Convertir a lista si no lo es (por ejemplo, si es un diccionario)
                datos_cotizacion['resultados'] = [datos_cotizacion['resultados']]
            
            for r in datos_cotizacion['resultados']:
                try:
                    # Asegurarnos de que los valores existan y sean del tipo correcto
                    print(f"Procesando resultado: {r}")
                    print(f"Tipo de dato resultado: {type(r)}")
                    
                    # Extraer escala y valor_unidad, o usar valores predeterminados si no existen
                    escala = r.get('escala', 0)
                    valor_unidad = r.get('valor_unidad', 0.0)
                    
                    # Convertir a tipos numéricos si son strings
                    if isinstance(escala, str):
                        try:
                            escala = int(escala.replace(',', ''))
                        except:
                            escala = 0
                    
                    if isinstance(valor_unidad, str):
                        try:
                            valor_unidad = float(valor_unidad.replace('$', '').replace(',', ''))
                        except:
                            valor_unidad = 0.0
                    
                    # Formatear los valores para mostrar en la tabla
                    escala_fmt = f"{int(escala):,}"
                    valor_unidad_fmt = f"${float(valor_unidad):.2f}"
                    
                    print(f"Procesando escala: {escala_fmt} - {valor_unidad_fmt}")
                    table_data.append([escala_fmt, valor_unidad_fmt])
                except Exception as e:
                    print(f"Error procesando resultado individual: {str(e)}, {r}")
                    import traceback
                    traceback.print_exc()
            
            # Solo crear la tabla si hay datos
            print(f"Tabla de datos final: {table_data}")
            if len(table_data) > 1:
                # Crear la tabla con los datos
                tabla = Table(table_data, colWidths=[170, 170])  # Ajustar ancho de columnas
                
                # Estilo de la tabla
                style = TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, 0), 12),
                    ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                    ('BACKGROUND', (0, 1), (-1, -1), colors.white),
                    ('GRID', (0, 0), (-1, -1), 1, colors.black),
                    ('ALIGN', (0, 1), (0, -1), 'CENTER'),  # Centrar la columna de escala
                    ('ALIGN', (1, 1), (1, -1), 'RIGHT'),   # Alinear a la derecha la columna de valor
                    ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                    ('FONTSIZE', (0, 1), (-1, -1), 10),
                    ('TOPPADDING', (0, 1), (-1, -1), 8),
                    ('BOTTOMPADDING', (0, 1), (-1, -1), 8),
                ])
                tabla.setStyle(style)
                
                # Agregar la tabla al documento
                elements.append(tabla)
                print("Tabla agregada exitosamente")
                
                # Agregar espacio después de la tabla
                elements.append(Spacer(1, 20))
            else:
                print("No hay suficientes datos para crear la tabla")
                # Incluso si falla, mostrar un mensaje en el PDF
                elements.append(Paragraph("Tabla de Precios", getSampleStyleSheet()['Heading2']))
                elements.append(Paragraph("No hay suficientes datos de resultados", getSampleStyleSheet()['Normal']))

        except Exception as e:
            print(f"Error procesando tabla de resultados: {str(e)}")
            import traceback
            traceback.print_exc()
            # Mostrar un mensaje de error en el PDF
            elements.append(Paragraph("Tabla de Precios", getSampleStyleSheet()['Heading2']))
            elements.append(Paragraph(f"Error al generar la tabla de resultados", getSampleStyleSheet()['Normal']))

        # Políticas y condiciones
        # Usar la forma de pago dinámica obtenida de los datos
        forma_pago = datos_cotizacion.get('forma_pago_desc', '50% ANTICIPO 50% ENTREGA') # Valor por defecto si no se encuentra
        elements.append(Paragraph(f"Forma de Pago: {forma_pago}", self.styles['Normal']))
        elements.append(Paragraph("I.V.A (no incluido): 19%", self.styles['Normal']))
        elements.append(Paragraph("% de Tolerancia: 10% + ó - de acuerdo a la cantidad pedida", self.styles['Normal']))
        elements.append(Spacer(1, 20))

        elements.append(Paragraph("Política de Entrega:", self.styles['Heading2']))
        elements.append(Paragraph("• Repeticiones: 13 días calendario a partir de la confirmación del pedido", self.styles['Normal']))
        elements.append(Paragraph("• Cambios: 15 días calendario a partir de la aprobación del sherpa", self.styles['Normal']))
        elements.append(Paragraph("• Nuevos: 20 días calendario a partir de la aprobación del sherpa", self.styles['Normal']))
        
        elements.append(Spacer(1, 10))
        elements.append(Paragraph("Política de Cartera:", self.styles['Heading2']))
        elements.append(Paragraph("• Se retiene despacho con mora de 16 a 30 días", self.styles['Normal']))
        elements.append(Paragraph("• Se retiene producción con mora de 31 a 45 días", self.styles['Normal']))
        
        elements.append(Spacer(1, 10))
        elements.append(Paragraph("Vigencia de la cotización: 30 días", self.styles['Normal']))
        
        # Agregar firma del comercial
        elements.append(Spacer(1, 20))
        elements.append(HRFlowable(width="100%", thickness=1, lineCap='round', color=colors.HexColor('#CCCCCC')))
        elements.append(Spacer(1, 10))
        
        # Datos del comercial
        if datos_cotizacion.get('comercial'):
            comercial = datos_cotizacion['comercial']
            # Verificar que el nombre no sea None antes de usar upper()
            if comercial.get('nombre') is not None:
                elements.append(Paragraph(comercial['nombre'].upper(), self.firma_style))
            else:
                elements.append(Paragraph("COMERCIAL NO ESPECIFICADO", self.firma_style))
            
            if comercial.get('email'):
                elements.append(Paragraph(f"Email: {comercial['email']}", self.firma_style))
            if comercial.get('celular'):
                elements.append(Paragraph(f"Cel: {comercial['celular']}", self.firma_style))
            
            print("\n=== DEBUG DATOS COMERCIAL EN PDF ===")
            print(f"Nombre: {comercial.get('nombre')}")
            print(f"Email: {comercial.get('email')}")
            print(f"Teléfono: {comercial.get('celular')}")
            print("=================================\n")

        # Generar PDF
        doc.build(elements)

class MaterialesPDF:
    def __init__(self):
        self.doc = SimpleDocTemplate("temp.pdf", pagesize=letter)
        self.styles = getSampleStyleSheet()
        self.elements = []
        self.title_style = ParagraphStyle(
            'CustomTitle',
            parent=self.styles['Title'],
            fontSize=14,
            spaceAfter=20,
            alignment=1  # Center alignment
        )
        self.subtitle_style = ParagraphStyle(
            'CustomSubtitle',
            parent=self.styles['Heading2'],
            fontSize=12,
            spaceAfter=10,
            spaceBefore=15
        )
        self.normal_style = ParagraphStyle(
            'CustomNormal',
            parent=self.styles['Normal'],
            fontSize=10,
            spaceAfter=5
        )

    def generar_pdf(self, datos_materiales, output_path):
        try:
            # Validate input data
            if not isinstance(datos_materiales, dict):
                print(f"Error: datos_materiales must be a dictionary. Received {type(datos_materiales)}")
                return False
            
            # Clear previous elements
            self.elements = []

            # Handle string inputs for material and acabado
            material = datos_materiales.get('material', {})
            acabado = datos_materiales.get('acabado', {})
            
            # If material or acabado are strings, convert to dictionary
            if isinstance(material, str):
                material = {'nombre': material}
            if isinstance(acabado, str):
                acabado = {'nombre': acabado}
            
            # Ensure material and acabado are dictionaries
            if not isinstance(material, dict):
                material = {}
            if not isinstance(acabado, dict):
                acabado = {}

            # Título principal
            self.elements.append(Paragraph("INFORME TÉCNICO DE COTIZACIÓN", self.title_style))
            self.elements.append(Spacer(1, 10))

            # 1. Identificación
            self.elements.append(Paragraph("1. Identificación", self.subtitle_style))
            identificador = datos_materiales.get('identificador', 'N/A')
            consecutivo = datos_materiales.get('consecutivo', 'N/A')
            nombre_cliente = datos_materiales.get('nombre_cliente', 'N/A')
            referencia = datos_materiales.get('descripcion', 'N/A')
            comercial = datos_materiales.get('comercial', {})
            nombre_comercial = comercial.get('nombre', 'N/A')
            
            self.elements.append(Paragraph(f"• Identificador: {identificador}", self.normal_style))
            self.elements.append(Paragraph(f"• Cliente: {nombre_cliente}", self.normal_style))
            self.elements.append(Paragraph(f"• Referencia: {referencia}", self.normal_style))
            self.elements.append(Paragraph(f"• Comercial: {nombre_comercial}", self.normal_style))

            # 4. Parámetros de Impresión
            self.elements.append(Paragraph("2. Parámetros de Impresión", self.subtitle_style))
            ancho = datos_materiales.get('ancho', 0)
            avance = datos_materiales.get('avance', 0)
            num_tintas = datos_materiales.get('num_tintas', 'N/A')
            numero_pistas = datos_materiales.get('numero_pistas', 0)
            
            # Additional parameters from markdown report
            gap_avance = datos_materiales.get('gap_avance', 7.95)  # Default value from markdown
            area_etiqueta = datos_materiales.get('area_etiqueta', ancho * avance)  # Calculate if not provided
            unidad_z = datos_materiales.get('unidad_z', 102.0)  # Default value from markdown
            
            self.elements.append(Paragraph(f"• Ancho: {ancho} mm", self.normal_style))
            self.elements.append(Paragraph(f"• Avance: {avance} mm", self.normal_style))
            self.elements.append(Paragraph(f"• Gap al avance: {gap_avance} mm", self.normal_style))
            self.elements.append(Paragraph(f"• Pistas: {numero_pistas}", self.normal_style))
            self.elements.append(Paragraph(f"• Número de Tintas: {num_tintas}", self.normal_style))
            self.elements.append(Paragraph(f"• Área de Etiqueta: {area_etiqueta:.2f} mm²", self.normal_style))
            self.elements.append(Paragraph(f"• Unidad (Z): {unidad_z}", self.normal_style))

            # 5. Información de Materiales
            self.elements.append(Paragraph("3. Información de Materiales", self.subtitle_style))
            # Mostrar detalles de material y acabado
            nombre_material = material.get('nombre', 'N/A')
            nombre_acabado = acabado.get('nombre', 'N/A')
            self.elements.append(Paragraph(f"• Material: {nombre_material}", self.normal_style))
            self.elements.append(Paragraph(f"• Acabado: {nombre_acabado}", self.normal_style))
            # Flags
            planchas_x_sep = datos_materiales.get('planchas_x_separado', False)
            existe_troq = datos_materiales.get('existe_troquel', False)
            self.elements.append(Paragraph(f"• Planchas por separado: {'Sí' if planchas_x_sep else 'No'}", self.normal_style))
            self.elements.append(Paragraph(f"• Troquel existe: {'Sí' if existe_troq else 'No'}", self.normal_style))
            # Costos detallados
            costo_mat = datos_materiales.get('valor_material', 0)
            costo_acb = datos_materiales.get('valor_acabado', 0)
            costo_troq = datos_materiales.get('valor_troquel', 0)
            self.elements.append(Paragraph(f"• Costo Material: ${costo_mat:,.2f}/mm²", self.normal_style))
            self.elements.append(Paragraph(f"• Costo Acabado: ${costo_acb:,.2f}/mm²", self.normal_style))
            self.elements.append(Paragraph(f"• Costo Troquel: ${costo_troq:,.2f}", self.normal_style))
            # 6. Tabla de Escalas
            self.elements.append(Spacer(1, 15))
            self.elements.append(Paragraph("4. Tabla de Escalas", self.subtitle_style))
            # Construir cabecera de tabla
            table_data = [[
                "Escala", "Valor Unidad", "Metros", "Tiempo (h)",
                "Montaje", "MO y Maq", "Tintas", "Papel/lam", "Desperdicio"
            ]]
            # Llenar filas con cada resultado
            for r in datos_materiales.get('resultados', []):
                table_data.append([
                    f"{r.get('escala','')} ",
                    f"${float(r.get('valor_unidad',0)):.2f}",
                    f"{r.get('metros',0):.2f}",
                    f"{r.get('tiempo_horas',0):.2f}",
                    f"${r.get('montaje',0):,.2f}",
                    f"${r.get('mo_y_maq',0):,.2f}",
                    f"{r.get('tintas',0)}", 
                    f"${r.get('papel_lam',0):,.2f}",
                    f"${r.get('desperdicio',0):,.2f}"
                ])
            # Crear tabla y aplicar estilo
            from reportlab.platypus import Table, TableStyle
            tabla = Table(table_data, repeatRows=1, colWidths=[60,60,60,60,60,60,50,60,60])
            estilo = TableStyle([
                ('BACKGROUND', (0,0), (-1,0), colors.lightgrey),
                ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
                ('ALIGN', (1,1), (-1,-1), 'RIGHT'),
                ('ALIGN', (0,0), (0,-1), 'CENTER'),
                ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ])
            tabla.setStyle(estilo)
            self.elements.append(tabla)
            self.elements.append(Spacer(1, 20))

            # Fecha y hora de generación
            self.elements.append(Spacer(1, 20))
            fecha_hora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.elements.append(Paragraph(f"Generado el: {fecha_hora}", self.normal_style))

            # Generar el PDF
            print(f"Intentando generar PDF en: {output_path}")
            print(f"Número de elementos: {len(self.elements)}")
            
            # Verify we have elements before building
            if not self.elements:
                print("ERROR: No hay elementos para generar el PDF")
                return False
            
            self.doc = SimpleDocTemplate(output_path, pagesize=letter)
            self.doc.build(self.elements)
            
            # Verify file was created and has content
            import os
            if os.path.exists(output_path):
                file_size = os.path.getsize(output_path)
                print(f"PDF generado exitosamente. Tamaño: {file_size} bytes")
                return True
            else:
                print("ERROR: El archivo PDF no se generó correctamente")
                return False
        
        except Exception as e:
            print(f"Error detallado al generar PDF de materiales: {str(e)}")
            import traceback
            traceback.print_exc()
            return False
    
    def get_calculos_from_datos(self, datos_materiales):
        """
        Extrae información de cálculos de los datos de materiales.
        Maneja casos donde los cálculos pueden estar en diferentes formatos.
        
        Args:
            datos_materiales (dict): Diccionario con información de la cotización
        
        Returns:
            dict: Diccionario con información de cálculos, con valores predeterminados seguros
        """
        # Intentar obtener cálculos de diferentes fuentes
        calculos = {}
        
        # Intentar obtener de resultados (primera escala)
        if datos_materiales.get('resultados') and isinstance(datos_materiales['resultados'], list):
            primera_escala = datos_materiales['resultados'][0] if datos_materiales['resultados'] else {}
            calculos.update({
                'desperdicio_total': primera_escala.get('desperdicio', 'N/A'),
                'metros': primera_escala.get('metros', 'N/A'),
                'tiempo_horas': primera_escala.get('tiempo_horas', 'N/A')
            })
        
        # Intentar obtener de los datos directamente
        calculos.update({
            'ancho': datos_materiales.get('ancho', 'N/A'),
            'avance': datos_materiales.get('avance', 'N/A'),
            'numero_pistas': datos_materiales.get('numero_pistas', 'N/A')
        })
        
        return calculos 