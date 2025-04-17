from supabase import create_client, Client
from typing import List, Optional, Dict, Any, Tuple
from model_classes.cotizacion_model import Cotizacion, Material, Acabado, Cliente, Comercial, Escala, ReferenciaCliente, TipoProducto, PrecioEscala, TipoGrafado
import os
import logging
from dotenv import load_dotenv
from datetime import datetime
import streamlit as st
import math
import sqlite3
import traceback
import re
import json
import sys
import io
import postgrest
import httpx
import time

class DBManager:
    def __init__(self, supabase_client):
        self.supabase = supabase_client
        
    def _generar_identificador(self, tipo_producto: str, material_code: str, ancho: float, avance: float,
                           num_pistas: int, num_tintas: int, acabado_code: str, num_paquetes_rollos: int,
                           cliente: str, referencia: str, numero_cotizacion: int) -> str:
        """Genera un identificador único para la cotización con el siguiente formato:
        TIPO MATERIAL ANCHO_x_AVANCE TINTAS [ACABADO] [RX/MX_PAQUETES] CLIENTE REFERENCIA NUMERO_COTIZACION"""
        # 1. Tipo de producto
        es_manga = "MANGA" in tipo_producto.upper()
        tipo = "MT" if es_manga else "ET"  # Usar MT para mangas, ET para etiquetas
        
        # 2. Código de material ya viene como parámetro
        if material_code and '-' in material_code:
            material_code = material_code.split('-')[0].strip()
        
        # 3. Formato ancho x avance
        dimensiones = f"{ancho:.0f}x{avance:.0f}"
        
        # 4. Número de tintas
        tintas = f"{num_tintas}T"
        
        # 7. Cliente (nombre completo, eliminando texto entre paréntesis)
        cliente_limpio = cliente.split('(')[0].strip().upper() if cliente else ""
        
        # 8. Referencia (descripción completa, eliminando texto entre paréntesis)
        referencia_limpia = referencia.split('(')[0].strip().upper() if referencia else ""
        
        # 9. Número de cotización con 4 dígitos
        num = f"{numero_cotizacion:04d}"
        
        # Construir el identificador según sea manga o etiqueta
        if es_manga:
            # Para mangas: TIPO MATERIAL ANCHO_x_AVANCE TINTAS MX_PAQUETES CLIENTE REFERENCIA NUMERO_COTIZACION
            paquetes = f"MX{num_paquetes_rollos}"
            identificador = f"{tipo} {material_code} {dimensiones} {tintas} {paquetes} {cliente_limpio} {referencia_limpia} {num}"
        else:
            # Para etiquetas: TIPO MATERIAL ANCHO_x_AVANCE TINTAS ACABADO RX_PAQUETES CLIENTE REFERENCIA NUMERO_COTIZACION
            # Extraer solo la parte antes del guión para el acabado
            acabado_code_limpio = ""
            if acabado_code:
                acabado_code_limpio = acabado_code.split('-')[0].strip()
            
            paquetes = f"RX{num_paquetes_rollos}"
            
            # Si hay código de acabado, incluirlo en el identificador
            if acabado_code_limpio:
                identificador = f"{tipo} {material_code} {dimensiones} {tintas} {acabado_code_limpio} {paquetes} {cliente_limpio} {referencia_limpia} {num}"
            else:
                # Si no hay código de acabado, omitirlo completamente
                identificador = f"{tipo} {material_code} {dimensiones} {tintas} {paquetes} {cliente_limpio} {referencia_limpia} {num}"
        
        # Convertir a mayúsculas
        identificador_final = identificador.upper()
        print(f"Identificador generado: {identificador_final}")
        
        return identificador_final
    
    def _retry_operation(self, operation_name: str, operation_func, max_retries=3, initial_delay=1):
        """
        Método auxiliar para reintentar operaciones de Supabase con manejo de errores.
        
        Args:
            operation_name (str): Nombre de la operación para logs
            operation_func (callable): Función a ejecutar
            max_retries (int): Número máximo de reintentos
            initial_delay (int): Retraso inicial en segundos antes de reintentar
        
        Returns:
            El resultado de la operación si es exitosa
        
        Raises:
            Exception: Si todos los reintentos fallan
        """
        last_error = None
        delay = initial_delay

        for attempt in range(max_retries):
            try:
                return operation_func()
            except httpx.RemoteProtocolError as e:
                last_error = e
                if attempt < max_retries - 1:
                    print(f"Error de conexión en {operation_name} (intento {attempt + 1}/{max_retries}): {str(e)}")
                    print(f"Reintentando en {delay} segundos...")
                    time.sleep(delay)
                    delay *= 2  # Backoff exponencial
                continue
            except Exception as e:
                # Para otros errores, los propagamos inmediatamente
                raise e

        # Si llegamos aquí, todos los reintentos fallaron
        error_msg = f"Error de conexión en {operation_name} después de {max_retries} intentos: {str(last_error)}"
        print(error_msg)
        raise Exception(error_msg)
        
    def _limpiar_datos(self, datos_dict: Dict[str, Any]) -> Dict[str, Any]:
        """
        Limpia los datos antes de enviarlos a la base de datos:
        - Elimina campos None
        - Elimina campos de fecha manejados por la BD
        - Convierte valores según el tipo de columna en la base de datos
        """
        campos_fecha = ['creado_en', 'actualizado_en', 'created_at', 'updated_at']
        campos_booleanos = ['es_manga', 'existe_troquel', 'es_recotizacion', 'troquel_existe']
        campos_enteros = ['cliente_id', 'referencia_id', 'material_id', 'acabado_id', 
                         'num_tintas', 'num_rollos', 'consecutivo', 'planchas_x_separado',
                         'numero_pistas', 'referencia_cliente_id', 'num_paquetes_rollos',
                         'tipo_producto_id', 'etiquetas_por_rollo']
        campos_numericos = ['valor_troquel', 'valor_plancha_separado', 'avance']
        campos_string = ['comercial_id']
        
        new_dict = {}
        for k, v in datos_dict.items():
            if v is not None and k not in campos_fecha:
                if k in campos_booleanos:
                    # Convertir a booleano
                    if isinstance(v, str):
                        new_dict[k] = v.lower() == 'true'
                    else:
                        new_dict[k] = bool(v)
                elif k in campos_enteros and v != '':
                    # Convertir a entero si no está vacío
                    try:
                        new_dict[k] = int(v) if v is not None else None
                    except (ValueError, TypeError):
                        new_dict[k] = None
                elif k in campos_numericos and v != '':
                    # Convertir a float para campos numéricos
                    try:
                        new_dict[k] = float(v) if v is not None else None
                    except (ValueError, TypeError):
                        new_dict[k] = None
                elif k in campos_string:
                    # Asegurar que estos campos sean string o None
                    new_dict[k] = str(v) if v is not None else None
                else:
                    # Mantener el valor original para otros campos
                    new_dict[k] = v
        
        return new_dict

    def obtener_proximo_consecutivo(self, tipo_documento: str = "COTIZACION") -> int:
        """
        Obtiene el próximo número consecutivo para un tipo de documento.
        
        Args:
            tipo_documento (str): Tipo de documento para el cual se genera el consecutivo.
        
        Returns:
            int: El próximo número consecutivo.
        
        Raises:
            Exception: Si hay problemas para obtener el consecutivo.
        """
        try:
            # Validar el tipo de documento
            if not tipo_documento or not isinstance(tipo_documento, str):
                raise ValueError("Tipo de documento inválido")
            
            print(f"\n=== OBTENIENDO CONSECUTIVO PARA {tipo_documento} ===")
            
            # Llamar a la función de base de datos para obtener el próximo consecutivo
            response = self.supabase.rpc(
                'obtener_proximo_consecutivo', 
                {'p_tipo_documento': tipo_documento}
            ).execute()
            
            if not response.data:
                # Si la función RPC no está disponible o falla, usamos el método alternativo
                return self.get_next_numero_cotizacion()
            
            # Extraer y validar el consecutivo
            consecutivo = response.data
            
            print(f"Consecutivo extraído: {consecutivo}")
            
            # Validar que el consecutivo sea un número entero positivo
            if not isinstance(consecutivo, int) or consecutivo <= 0:
                raise ValueError(f"Consecutivo inválido generado: {consecutivo}")
            
            print(f"=== CONSECUTIVO GENERADO: {consecutivo} ===\n")
            return consecutivo
        
        except Exception as e:
            # Registrar el error para depuración
            error_msg = f"Error al obtener consecutivo para {tipo_documento}: {str(e)}"
            print(error_msg)
            logging.error(error_msg)
            
            # Intentamos el método alternativo
            return self.get_next_numero_cotizacion()

    def get_next_numero_cotizacion(self) -> int:
        """Obtiene el siguiente número de cotización disponible."""
        try:
            response = (
                self.supabase.from_('cotizaciones')
                .select('numero_cotizacion')
                .order('numero_cotizacion', desc=True)
                .limit(1)
                .execute()
            )
            
            if response.data and len(response.data) > 0 and response.data[0].get('numero_cotizacion') is not None:
                ultimo_numero = response.data[0]['numero_cotizacion']
                # Asegurar que sea un entero
                try:
                    ultimo_numero = int(ultimo_numero)
                    return ultimo_numero + 1
                except (ValueError, TypeError):
                    print(f"Error convirtiendo numero_cotizacion a entero: {ultimo_numero}")
                    return 1
            else:
                return 1
            
        except Exception as e:
            print(f"Error al obtener el siguiente número de cotización: {str(e)}")
            return 1

    def crear_cotizacion(self, datos_cotizacion):
        """Crea una nueva cotización."""
        def _operation():
            # Generar número de cotización si no existe
            if 'numero_cotizacion' not in datos_cotizacion or not datos_cotizacion['numero_cotizacion']:
                numero_cotizacion = self.obtener_proximo_consecutivo()
                if not numero_cotizacion:
                    return None
                datos_cotizacion['numero_cotizacion'] = numero_cotizacion
            
            # Convertir valores Decimal a float para JSON
            for key in ['valor_troquel', 'valor_plancha_separado']:
                if key in datos_cotizacion and datos_cotizacion[key] is not None:
                    try:
                        datos_cotizacion[key] = float(datos_cotizacion[key])
                    except (TypeError, ValueError):
                        print(f"Error convirtiendo {key} a float")
                        datos_cotizacion[key] = 0.0
            
            # Obtener datos necesarios para generar el identificador
            print("\nGenerando identificador único...")
            
            # Obtener el tipo de producto
            tipo_producto = "MANGA" if datos_cotizacion.get('es_manga') else "ETIQUETA"
            
            # Obtener códigos de material y acabado
            material_code = self.get_material_code(datos_cotizacion.get('material_id'))
            acabado_code = self.get_acabado_code(datos_cotizacion.get('acabado_id')) if not datos_cotizacion.get('es_manga') else ""
            
            # Obtener la referencia para acceder al cliente
            referencia = self.get_referencia_cliente(datos_cotizacion.get('referencia_cliente_id'))
            if not referencia:
                raise ValueError(f"No se encontró la referencia con ID {datos_cotizacion.get('referencia_cliente_id')}")
            
            # Obtener el cliente
            cliente = self.get_cliente(referencia.cliente_id)
            if not cliente:
                raise ValueError(f"No se encontró el cliente con ID {referencia.cliente_id}")
            
            # Generar el identificador
            identificador = self._generar_identificador(
                tipo_producto=tipo_producto,
                material_code=material_code,
                ancho=datos_cotizacion.get('ancho', 0),
                avance=datos_cotizacion.get('avance', 0),
                num_pistas=datos_cotizacion.get('numero_pistas', 1),
                num_tintas=datos_cotizacion.get('num_tintas', 0),
                acabado_code=acabado_code,
                num_paquetes_rollos=datos_cotizacion.get('num_paquetes_rollos', 0),
                cliente=cliente.nombre,
                referencia=referencia.descripcion,
                numero_cotizacion=datos_cotizacion['numero_cotizacion']
            )
            
            # Agregar el identificador a los datos
            datos_cotizacion['identificador'] = identificador
            print(f"Identificador generado: {identificador}")
            
            print("\nDatos a insertar en cotización:")
            for k, v in datos_cotizacion.items():
                print(f"  {k}: {v}")
            
            # Insertar la cotización
            result = self.supabase.from_('cotizaciones').insert(datos_cotizacion).execute()
            
            if result.data and len(result.data) > 0:
                return result.data[0]
            print("Error al crear la cotización: no se recibió respuesta del servidor")
            return None

        try:
            return self._retry_operation("crear cotización", _operation)
        except Exception as e:
            print(f"Error al crear cotización: {str(e)}")
            traceback.print_exc()
            return None

    def actualizar_cotizacion(self, cotizacion_id, datos_cotizacion):
        """
        Actualiza una cotización existente
        """
        try:
            # Actualizar la cotización
            result = self.supabase.from_('cotizaciones') \
                .update(datos_cotizacion) \
                .eq('id', cotizacion_id) \
                .execute()
            
            if result.data and len(result.data) > 0:
                return result.data[0]
            return None
            
        except Exception as e:
            print(f"Error al actualizar cotización: {str(e)}")
            return None

    def guardar_cotizacion_escalas(self, cotizacion_id: int, escalas: List[Escala]) -> bool:
        """Guarda las escalas de una cotización"""
        def _operation():
            if not cotizacion_id:
                print("Error: cotizacion_id es requerido")
                return False

            print(f"\n=== INICIO GUARDAR_COTIZACION_ESCALAS para cotización {cotizacion_id} ===")
            print(f"Número de escalas a guardar: {len(escalas)}")
            
            # Eliminar escalas anteriores si existen
            print("Eliminando escalas anteriores...")
            delete_result = self.supabase.from_('cotizacion_escalas') \
                .delete() \
                .eq('cotizacion_id', cotizacion_id) \
                .execute()
            print(f"Resultado de eliminación: {delete_result.data if hasattr(delete_result, 'data') else 'No data'}")
            
            # Preparar datos de las escalas
            escalas_data = []
            for escala in escalas:
                print(f"\nProcesando escala: {escala}")
                datos_escala = {
                    'cotizacion_id': cotizacion_id,
                    'escala': escala.escala,
                    'valor_unidad': escala.valor_unidad,
                    'metros': escala.metros,
                    'tiempo_horas': escala.tiempo_horas,
                    'montaje': escala.montaje,
                    'mo_y_maq': escala.mo_y_maq,
                    'tintas': escala.tintas,
                    'papel_lam': escala.papel_lam,
                    'desperdicio_total': escala.desperdicio_total
                }
                print("Datos de escala a insertar:", datos_escala)
                escalas_data.append(datos_escala)
            
            if escalas_data:
                print(f"\nInsertando {len(escalas_data)} escalas...")
                insert_result = self.supabase.from_('cotizacion_escalas') \
                    .insert(escalas_data) \
                    .execute()
                print(f"Resultado de inserción: {insert_result.data if hasattr(insert_result, 'data') else 'No data'}")
                
                if not insert_result.data:
                    print("Error: No se recibió confirmación de la inserción de escalas")
                    return False
                    
                print(f"Se insertaron {len(insert_result.data)} escalas correctamente")
            else:
                print("No hay escalas para insertar")
            
            print("=== FIN GUARDAR_COTIZACION_ESCALAS ===\n")
            return True

        try:
            return self._retry_operation("guardar escalas de cotización", _operation)
        except Exception as e:
            print(f"Error al guardar escalas: {e}")
            traceback.print_exc()
            return False

    def obtener_cotizacion(self, cotizacion_id):
        """
        Obtiene una cotización por su ID
        """
        try:
            # Obtener la cotización
            result = self.supabase.from_('cotizaciones').select('*').eq('id', cotizacion_id).execute()
            
            if result.data and len(result.data) > 0:
                cotizacion = result.data[0]
                
                # Obtener las escalas
                escalas = self.get_cotizacion_escalas(cotizacion_id)
                if escalas:
                    cotizacion['escalas'] = escalas
                
                return cotizacion
            else:
                print(f"No se encontró la cotización con ID {cotizacion_id}")
                return None
                
        except Exception as e:
            print(f"Error al obtener cotización: {str(e)}")
            return None

    def get_materiales(self) -> List[Material]:
        """Obtiene todos los materiales disponibles."""
        def _operation():
            response = self.supabase.from_('materiales').select(
                'id, nombre, valor, updated_at, code, id_adhesivos, adhesivos(tipo)'
            ).execute()
            
            if not response.data:
                logging.warning("No se encontraron materiales")
                return []
            
            materiales = []
            for item in response.data:
                material_data = {
                    'id': item['id'],
                    'nombre': item['nombre'],
                    'valor': item['valor'],
                    'updated_at': item['updated_at'],
                    'code': item['code'],
                    'id_adhesivos': item['id_adhesivos'],
                    'adhesivo_tipo': item['adhesivos']['tipo'] if item['adhesivos'] else None
                }
                materiales.append(Material(**material_data))
            
            return materiales

        try:
            return self._retry_operation("obtener materiales", _operation)
        except Exception as e:
            logging.error(f"Error al obtener materiales: {str(e)}")
            raise

    def get_material(self, material_id: int) -> Optional[Material]:
        """Obtiene un material específico por su ID."""
        try:
            response = self.supabase.from_('materiales').select(
                'id, nombre, valor, updated_at, code, id_adhesivos, adhesivos(tipo)'
            ).eq('id', material_id).execute()
            
            if not response.data or len(response.data) == 0:
                print(f"No se encontró material con ID {material_id}")
                return None
            
            # Procesar el resultado para aplanar la estructura
            item = response.data[0]
            material_data = {
                'id': item['id'],
                'nombre': item['nombre'],
                'valor': item['valor'],
                'updated_at': item['updated_at'],
                'code': item['code'],
                'id_adhesivos': item['id_adhesivos'],
                'adhesivo_tipo': item['adhesivos']['tipo'] if item['adhesivos'] else None
            }
            
            return Material(**material_data)
            
        except Exception as e:
            print(f"Error al obtener material: {e}")
            traceback.print_exc()
            return None

    def get_material_code(self, material_id: int) -> str:
        """Obtiene el código del material por su ID"""
        try:
            response = self.supabase.table('materiales').select('code').eq('id', material_id).execute()
            if response.data and len(response.data) > 0:
                return response.data[0]['code']
            return ""
        except Exception as e:
            print(f"Error al obtener código de material: {e}")
            return ""

    def get_acabados(self) -> List[Acabado]:
        """Obtiene todos los acabados disponibles."""
        try:
            response = self.supabase.table('acabados').select('*').execute()
            if not response.data:
                logging.warning("No se encontraron acabados")
            return [Acabado(**item) for item in response.data]
        except Exception as e:
            logging.error(f"Error al obtener acabados: {str(e)}")
            raise

    def get_acabado(self, acabado_id: int) -> Optional[Acabado]:
        """Obtiene un acabado específico por su ID."""
        try:
            response = self.supabase.from_('acabados').select('*').eq('id', acabado_id).execute()
            
            if not response.data or len(response.data) == 0:
                print(f"No se encontró acabado con ID {acabado_id}")
                return None
            
            # Crear y retornar un objeto Acabado
            acabado_data = response.data[0]
            return Acabado(**acabado_data)
            
        except Exception as e:
            print(f"Error al obtener acabado: {e}")
            traceback.print_exc()
            return None

    def get_acabado_code(self, acabado_id: int) -> str:
        """Obtiene el código del acabado por su ID"""
        try:
            response = self.supabase.table('acabados').select('code').eq('id', acabado_id).execute()
            if response.data and len(response.data) > 0:
                return response.data[0]['code']
            return ""
        except Exception as e:
            print(f"Error al obtener código de acabado: {e}")
            return ""

    def get_tipos_producto(self) -> List[TipoProducto]:
        """Obtiene todos los tipos de producto disponibles."""
        try:
            print("\n=== INICIO GET_TIPOS_PRODUCTO ===")
            response = self.supabase.from_('tipo_producto').select('*').execute()
            
            if not response.data:
                print("No se encontraron tipos de producto")
                return []
            
            tipos_producto = []
            for item in response.data:
                tipos_producto.append(TipoProducto(**item))
            
            print(f"Se encontraron {len(tipos_producto)} tipos de producto")
            print("=== FIN GET_TIPOS_PRODUCTO ===\n")
            return tipos_producto
            
        except Exception as e:
            print(f"Error al obtener tipos de producto: {e}")
            traceback.print_exc()
            return []

    def get_tipo_producto(self, tipo_producto_id: int) -> Optional[TipoProducto]:
        """Obtiene un tipo de producto específico por su ID."""
        try:
            response = self.supabase.from_('tipo_producto').select('*').eq('id', tipo_producto_id).execute()
            
            if not response.data or len(response.data) == 0:
                print(f"No se encontró tipo de producto con ID {tipo_producto_id}")
                return None
            
            # Crear y retornar un objeto TipoProducto
            return TipoProducto(**response.data[0])
            
        except Exception as e:
            print(f"Error al obtener tipo de producto: {e}")
            traceback.print_exc()
            return None

    def get_tipos_grafado(self) -> List[TipoGrafado]:
        """Obtiene todos los tipos de grafado disponibles."""
        try:
            print("\n=== INICIO GET_TIPOS_GRAFADO ===")
            response = self.supabase.from_('tipos_grafado').select('*').execute()
            
            if not response.data:
                print("No se encontraron tipos de grafado")
                return []
            
            tipos_grafado = []
            for item in response.data:
                tipos_grafado.append(TipoGrafado.from_dict(item))
            
            print(f"Se encontraron {len(tipos_grafado)} tipos de grafado")
            print("=== FIN GET_TIPOS_GRAFADO ===\n")
            return tipos_grafado
            
        except Exception as e:
            print(f"Error al obtener tipos de grafado: {e}")
            traceback.print_exc()
            return []

    def get_comerciales(self) -> List[Comercial]:
        """Obtiene todos los comerciales disponibles."""
        try:
            print("\n=== INICIO GET_COMERCIALES ===")
            response = self.supabase.table('comerciales').select('*').execute()
            
            if not response.data:
                print("No se encontraron comerciales")
                return []
            
            comerciales = []
            for item in response.data:
                comerciales.append(Comercial(**item))
            
            print(f"Se encontraron {len(comerciales)} comerciales")
            print("=== FIN GET_COMERCIALES ===\n")
            return comerciales
        except Exception as e:
            print(f"Error al obtener comerciales: {e}")
            traceback.print_exc()
            return []

    def get_comercial(self, comercial_id: str) -> Optional[Comercial]:
        """Obtiene un comercial específico por su ID."""
        try:
            print(f"\n=== INICIO GET_COMERCIAL {comercial_id} ===")
            response = self.supabase.from_('comerciales').select('*').eq('id', comercial_id).execute()
            
            if not response.data or len(response.data) == 0:
                print(f"No se encontró comercial con ID {comercial_id}")
                return None
                
            # Crear y retornar un objeto Comercial
            comercial_data = response.data[0]
            comercial = Comercial(**comercial_data)
            print(f"Comercial encontrado: {comercial.nombre}")
            print("=== FIN GET_COMERCIAL ===\n")
            return comercial
            
        except Exception as e:
            print(f"Error al obtener comercial: {e}")
            traceback.print_exc()
            return None

    def get_comercial_default(self) -> Optional[str]:
        """Obtiene el ID del comercial por defecto (primero de la lista)."""
        try:
            comerciales = self.get_comerciales()
            if comerciales and len(comerciales) > 0:
                return comerciales[0].id
            return 'faf071b9-a885-4d8a-b65e-6a3b3785334a'  # ID fijo por si falla
        except Exception as e:
            print(f"Error al obtener comercial por defecto: {e}")
            return 'faf071b9-a885-4d8a-b65e-6a3b3785334a'  # ID de comercial por defecto

    def get_clientes(self) -> List[Cliente]:
        """Obtiene todos los clientes disponibles."""
        def _operation():
            print("\n=== INICIO GET_CLIENTES ===")
            print("Intentando obtener clientes usando RPC...")
            
            response = self.supabase.rpc('obtener_clientes').execute()
            
            print("Respuesta de get_clientes:")
            print("Tipo de respuesta:", type(response))
            print("Datos en la respuesta:", response.data if hasattr(response, 'data') else None)
            
            if not response.data:
                print("No se encontraron clientes en la base de datos.")
                return []
            
            clientes = [Cliente(**item) for item in response.data]
            print(f"Número de clientes encontrados: {len(clientes)}")
            print("=== FIN GET_CLIENTES ===\n")
            return clientes

        try:
            return self._retry_operation("obtener clientes", _operation)
        except Exception as e:
            print(f"Error al obtener clientes: {e}")
            traceback.print_exc()
            raise

    def get_cliente(self, cliente_id: int) -> Optional[Cliente]:
        """Obtiene un cliente específico por su ID."""
        try:
            # Consulta para obtener el cliente
            response = self.supabase.from_('clientes').select('*').eq('id', cliente_id).execute()
            
            if not response.data or len(response.data) == 0:
                print(f"No se encontró cliente con ID {cliente_id}")
                return None
                
            # Crear y retornar un objeto Cliente
            cliente_data = response.data[0]
            return Cliente(**cliente_data)
            
        except Exception as e:
            print(f"Error al obtener cliente: {e}")
            traceback.print_exc()
            return None

    def ejecutar_sql(self, query: str) -> Any:
        """Ejecuta una consulta SQL directamente en la base de datos"""
        try:
            print(f"Ejecutando SQL: {query}")
            response = self.supabase.rpc('execute_sql', {'query': query}).execute()
            print(f"Respuesta: {response.data}")
            return response.data
        except Exception as e:
            print(f"Error al ejecutar SQL: {e}")
            traceback.print_exc()
            raise

    def crear_cliente(self, cliente: Cliente) -> Cliente:
        """Crea un nuevo cliente en la base de datos."""
        try:
            print("\n=== INICIO CREAR CLIENTE ===")
            print(f"Cliente recibido: {cliente}")
            
            # Usar _limpiar_datos para preparar los datos
            cliente_data = self._limpiar_datos(cliente.__dict__)
            print("\nDatos limpios del cliente a insertar:")
            for k, v in cliente_data.items():
                print(f"  {k}: {v}")
            
            # Intentar insertar usando RPC
            try:
                print("\nPreparando datos para RPC:")
                rpc_data = {
                    'p_nombre': cliente_data['nombre'],
                    'p_codigo': cliente_data.get('codigo'),
                    'p_persona_contacto': cliente_data.get('persona_contacto'),
                    'p_correo_electronico': cliente_data.get('correo_electronico'),
                    'p_telefono': cliente_data.get('telefono')
                }
                print("Datos RPC preparados:")
                for k, v in rpc_data.items():
                    print(f"  {k}: {v}")
                
                print("\nIniciando llamada RPC 'insertar_cliente'...")
                response = self.supabase.rpc(
                    'insertar_cliente',
                    rpc_data
                ).execute()
                
                print("\nRespuesta RPC recibida:")
                print(f"Tipo de respuesta: {type(response)}")
                print(f"Respuesta completa: {response}")
                print(f"Datos en response: {response.data if hasattr(response, 'data') else 'Sin datos'}")
                
                if not response.data:
                    raise Exception("No se pudo crear el cliente. Respuesta vacía.")
                
                print("\nCreando objeto Cliente con datos de respuesta:")
                print(f"Datos para crear Cliente: {response.data[0]}")
                nuevo_cliente = Cliente(**response.data[0])
                print(f"Cliente creado exitosamente: {nuevo_cliente}")
                
                print("\nVerificando cliente en la base de datos...")
                verify = self.supabase.table('clientes').select('*').eq('id', nuevo_cliente.id).execute()
                print(f"Verificación: {verify.data}")
                
                print("\n=== FIN CREAR CLIENTE ===")
                return nuevo_cliente
                
            except Exception as e:
                print("\n!!! ERROR DURANTE LA INSERCIÓN !!!")
                print(f"Tipo de error: {type(e)}")
                print(f"Mensaje de error: {str(e)}")
                print("Datos que se intentaron insertar:")
                for k, v in rpc_data.items():
                    print(f"  {k}: {v}")
                print("\nStack trace completo:")
                traceback.print_exc()
                raise Exception(f"Error al crear cliente: {str(e)}")
        
        except Exception as e:
            print("\n!!! ERROR GENERAL EN CREAR_CLIENTE !!!")
            print(f"Tipo de error: {type(e)}")
            print(f"Mensaje de error: {str(e)}")
            print("\nStack trace completo:")
            traceback.print_exc()
            raise

    def get_referencias_cliente(self, cliente_id: int) -> List[ReferenciaCliente]:
        """Obtiene las referencias de un cliente"""
        try:
            response = self.supabase.table('referencias_cliente').select(
                '*'
            ).eq('cliente_id', cliente_id).execute()
            referencias = []
            for data in response.data:
                referencia = ReferenciaCliente(
                    id=data['id'],
                    cliente_id=data['cliente_id'],
                    descripcion=data['descripcion'],
                    creado_en=data['creado_en'],
                    actualizado_en=data['actualizado_en'],
                    id_comercial=data['id_comercial'],
                    tiene_cotizacion=data.get('tiene_cotizacion', False)
                )
                referencias.append(referencia)
            return referencias
        except Exception as e:
            print(f"Error al obtener referencias del cliente: {e}")
            return []

    def get_referencia_cliente(self, referencia_id: int) -> Optional[ReferenciaCliente]:
        """Obtiene una referencia de cliente por su ID"""
        try:
            response = self.supabase.table('referencias_cliente').select(
                '*'
            ).eq('id', referencia_id).execute()
            if response.data:
                data = response.data[0]
                return ReferenciaCliente(
                    id=data['id'],
                    cliente_id=data['cliente_id'],
                    descripcion=data['descripcion'],
                    creado_en=data['creado_en'],
                    actualizado_en=data['actualizado_en'],
                    id_comercial=data['id_comercial'],
                    tiene_cotizacion=data.get('tiene_cotizacion', False)
                )
            return None
        except Exception as e:
            print(f"Error al obtener referencia del cliente: {e}")
            return None

    def crear_referencia(self, referencia: ReferenciaCliente) -> Optional[ReferenciaCliente]:
        """Crea una nueva referencia de cliente"""
        def _operation():
            # Validar datos requeridos
            if not referencia.cliente_id or not referencia.descripcion:
                print("Error: cliente_id y descripcion son requeridos")
                return None

            # Preparar datos básicos - solo los campos que existen en la tabla
            data = {
                'cliente_id': referencia.cliente_id,
                'descripcion': referencia.descripcion.strip(),
                'id_comercial': referencia.id_comercial
            }

            # Verificar si ya existe una referencia con la misma descripción para este cliente
            existing = self.supabase.table('referencias_cliente').select('*').eq('cliente_id', referencia.cliente_id).eq('descripcion', data['descripcion']).execute()
            if existing.data and len(existing.data) > 0:
                cliente = self.get_cliente(referencia.cliente_id)
                cliente_nombre = cliente.nombre if cliente else "este cliente"
                error_msg = (
                    f"⚠️ No se puede crear la referencia porque ya existe una con la misma descripción:\n\n"
                    f"Cliente: {cliente_nombre}\n"
                    f"Descripción: {data['descripcion']}\n\n"
                    "Por favor, utiliza una descripción diferente para esta referencia."
                )
                print(error_msg)
                raise ValueError(error_msg)

            # Insertar la referencia
            response = self.supabase.table('referencias_cliente').insert(data).execute()
            
            if response.data:
                # Actualizar el ID de la referencia y retornar
                referencia.id = response.data[0]['id']
                return referencia
            return None

        try:
            return self._retry_operation("crear referencia", _operation)
        except postgrest.exceptions.APIError as e:
            if e.code == '23505':  # Código de error para violación de restricción única
                cliente = self.get_cliente(referencia.cliente_id)
                cliente_nombre = cliente.nombre if cliente else "este cliente"
                error_msg = (
                    f"⚠️ No se puede crear la referencia porque ya existe una con la misma descripción:\n\n"
                    f"Cliente: {cliente_nombre}\n"
                    f"Descripción: {referencia.descripcion}\n\n"
                    "Por favor, utiliza una descripción diferente para esta referencia."
                )
                print(error_msg)
                raise ValueError(error_msg)
            print(f"Error al crear referencia: {e}")
            traceback.print_exc()
            raise e
        except ValueError as ve:
            # Re-lanzar errores de validación con el mensaje mejorado
            raise ve
        except Exception as e:
            # Modificado: Re-lanzar la excepción original en lugar de crear un ValueError genérico.
            error_msg = f"❌ Error inesperado al crear la referencia: {str(e)}"
            print(error_msg)
            traceback.print_exc()
            raise e

    def crear_referencia_cliente(self, referencia: ReferenciaCliente) -> Optional[int]:
        """Crea una nueva referencia de cliente en la base de datos."""
        try:
            print("\n=== INICIO CREAR REFERENCIA CLIENTE ===")
            print(f"Referencia recibida: {referencia}")
            
            # Preparar datos para la inserción
            datos_insercion = {
                'cliente_id': referencia.cliente_id,
                'descripcion': referencia.descripcion,
                'id_comercial': referencia.id_comercial,
                'tipo_producto_id': referencia.tipo_producto_id
            }
            
            print("\nDatos a insertar:")
            for k, v in datos_insercion.items():
                print(f"  {k}: {v}")
            
            # Insertar la referencia
            response = (
                self.supabase.table('referencias_cliente')
                .insert(datos_insercion)
                .execute()
            )
            
            print("\nRespuesta de la inserción:")
            print(f"Tipo de respuesta: {type(response)}")
            print(f"Datos: {response.data}")
            
            if not response.data:
                raise Exception("No se pudo crear la referencia. Respuesta vacía.")
            
            # Obtener el ID de la referencia creada
            referencia_id = response.data[0]['id']
            print(f"\nID de la referencia creada: {referencia_id}")
            
            print("=== FIN CREAR REFERENCIA CLIENTE ===\n")
            return referencia_id
            
        except Exception as e:
            print(f"Error al crear referencia: {e}")
            traceback.print_exc()
            raise

    def get_datos_completos_cotizacion(self, cotizacion_id: int) -> dict:
        """Obtiene todos los datos necesarios para generar el PDF de una cotización"""
        try:
            print("\n=== DEBUG GET_DATOS_COMPLETOS_COTIZACION ===")
            print(f"Obteniendo datos para cotización ID: {cotizacion_id}")
            
            # Obtener la cotización completa con todas sus relaciones
            response = (
                self.supabase.from_('cotizaciones')
                .select('''
                    *,
                    material:materiales!inner(*),
                    acabado:acabados(*),
                    referencia:referencias_cliente!fk_cotizaciones_referencia_cliente(
                        *,
                        cliente:clientes(*),
                        comercial:comerciales(*)
                    ),
                    tipo_producto:tipo_producto(*)
                ''')
                .eq('id', cotizacion_id)
                .execute()
            )
            
            if not response.data:
                print("No se encontró la cotización")
                return None
            
            cotizacion_data = response.data[0]
            print("\nDatos básicos de la cotización:")
            print(f"  ID: {cotizacion_data.get('id')}")
            
            # Extraer datos del cliente y comercial a través de la referencia
            referencia = cotizacion_data.get('referencia', {})
            cliente = referencia.get('cliente', {})
            comercial = referencia.get('comercial', {})
            
            print(f"  Cliente: {cliente.get('nombre')}")
            print(f"  Referencia: {referencia.get('descripcion')}")
            
            # Manejar caso donde tipo_producto puede ser None
            tipo_producto = cotizacion_data.get('tipo_producto')
            if tipo_producto is not None:
                print(f"  Tipo Producto: {tipo_producto.get('nombre')}")
            else:
                print("  Tipo Producto: No especificado")
            
            # Preparar el diccionario de datos
            datos = {
                'consecutivo': cotizacion_data.get('numero_cotizacion'),
                'nombre_cliente': cliente.get('nombre'),
                'descripcion': referencia.get('descripcion'),
                'material': cotizacion_data.get('material', {}),
                'acabado': cotizacion_data.get('acabado', {}),
                'num_tintas': cotizacion_data.get('num_tintas'),
                'num_rollos': cotizacion_data.get('num_paquetes_rollos'),
                'es_manga': cotizacion_data.get('es_manga'),
                'tipo_grafado': cotizacion_data.get('tipo_grafado_id'),
                'valor_plancha_separado': cotizacion_data.get('valor_plancha_separado'),
                'cliente': {
                    'id': cliente.get('id'),
                    'nombre': cliente.get('nombre'),
                    'codigo': cliente.get('codigo'),
                    'persona_contacto': cliente.get('persona_contacto'),
                    'correo_electronico': cliente.get('correo_electronico'),
                    'telefono': cliente.get('telefono')
                },
                'comercial': comercial,
                'identificador': cotizacion_data.get('identificador', '')
            }
            
            # También agregamos el tipo_producto si existe
            if tipo_producto is not None:
                datos['tipo_producto'] = tipo_producto
            
            print("\nDatos preparados para el PDF:")
            for k, v in datos.items():
                if k not in ['material', 'acabado', 'cliente', 'comercial', 'tipo_producto']: # Excluir objetos grandes
                    print(f"  {k}: {v}")
            
            # Obtener las escalas
            escalas_response = (
                self.supabase.from_('cotizacion_escalas')
                .select('*')
                .eq('cotizacion_id', cotizacion_id)
                .execute()
            )
            
            if escalas_response.data and len(escalas_response.data) > 0:
                print(f"\nEscalas encontradas: {len(escalas_response.data)}")
                datos['resultados'] = []
                for escala_data in escalas_response.data:
                    resultado = {
                        'escala': escala_data['escala'],
                        'valor_unidad': escala_data['valor_unidad'],
                        'metros': escala_data['metros'],
                        'tiempo_horas': escala_data['tiempo_horas'],
                        'montaje': escala_data['montaje'],
                        'mo_y_maq': escala_data['mo_y_maq'],
                        'tintas': escala_data['tintas'],
                        'papel_lam': escala_data['papel_lam'],
                        'desperdicio': escala_data['desperdicio_total']
                    }
                    print(f"  Escala: {resultado['escala']}, Valor unidad: {resultado['valor_unidad']}")
                    datos['resultados'].append(resultado)
                
                print(f"Total de resultados añadidos: {len(datos['resultados'])}")
            else:
                print("\nNo se encontraron escalas para esta cotización")
                datos['resultados'] = []
            
            # También agregar el ID de la cotización para referencia
            datos['id'] = cotizacion_id
            
            print("=== FIN GET_DATOS_COMPLETOS_COTIZACION ===\n")
            return datos
            
        except Exception as e:
            print(f"Error al obtener datos completos de la cotización: {e}")
            traceback.print_exc()
            return None

    def get_escala(self, escala_id: int) -> Optional[Escala]:
        """Obtiene una escala específica por su ID."""
        try:
            response = self.supabase.from_('cotizacion_escalas').select('*').eq('id', escala_id).execute()
            
            if not response.data or len(response.data) == 0:
                print(f"No se encontró escala con ID {escala_id}")
                return None
            
            # Crear y retornar un objeto Escala
            escala_data = response.data[0]
            return Escala(**escala_data)
            
        except Exception as e:
            print(f"Error al obtener escala: {e}")
            traceback.print_exc()
            return None

    def get_cotizacion_escalas(self, cotizacion_id: int) -> List[Escala]:
        """Obtiene todas las escalas asociadas a una cotización"""
        try:
            print(f"\n=== INICIO GET_COTIZACION_ESCALAS para cotización {cotizacion_id} ===")
            # Obtener las escalas
            response = self.supabase.from_('cotizacion_escalas').select('*').eq('cotizacion_id', cotizacion_id).execute()
            
            if not response.data:
                print("No se encontraron escalas")
                return []
            
            escalas = []
            for escala_data in response.data:
                # Crear objeto Escala
                escala = Escala.from_dict(escala_data)
                # Obtener y agregar precios asociados
                escala.precios = self.get_precios_escala(escala.id)
                escalas.append(escala)
            
            print(f"Se encontraron {len(escalas)} escalas")
            print("=== FIN GET_COTIZACION_ESCALAS ===\n")
            return escalas
            
        except Exception as e:
            print(f"Error obteniendo escalas de cotización: {e}")
            traceback.print_exc()
            return []

    def get_precios_escala(self, escala_id: int) -> List[PrecioEscala]:
        """Obtiene todos los precios asociados a una escala"""
        try:
            response = self.supabase.from_('precios_escala').select('*').eq('escala_id', escala_id).execute()
            
            if not response.data:
                return []
            
            return [PrecioEscala(**precio_data) for precio_data in response.data]
            
        except Exception as e:
            print(f"Error obteniendo precios de escala: {e}")
            traceback.print_exc()
            return []

    def referencia_tiene_cotizacion(self, referencia_id: int) -> bool:
        """Verifica si una referencia ya tiene una cotización asociada."""
        try:
            # Asegurarse de que referencia_id es un entero
            if not isinstance(referencia_id, int):
                try:
                    referencia_id = int(referencia_id)
                except (ValueError, TypeError):
                    print(f"Error: referencia_id debe ser un entero, se recibió: {referencia_id} de tipo {type(referencia_id)}")
                    return False
            
            response = (
                self.supabase.from_('cotizaciones')
                .select('id')
                .eq('referencia_cliente_id', referencia_id)
                .execute()
            )
            
            return response.data and len(response.data) > 0
            
        except Exception as e:
            print(f"Error al verificar si la referencia tiene cotización: {str(e)}")
            return False

    def corregir_tipo_producto_id(self, cotizacion_id: int, tipo_producto_id: int) -> bool:
        """
        Corrige el tipo_producto_id de una cotización existente.
        
        Args:
            cotizacion_id (int): ID de la cotización a corregir
            tipo_producto_id (int): Valor correcto para tipo_producto_id
            
        Returns:
            bool: True si la actualización fue exitosa, False en caso contrario
        """
        try:
            print(f"\n=== CORRIGIENDO TIPO_PRODUCTO_ID PARA COTIZACIÓN {cotizacion_id} ===")
            print(f"Nuevo valor para tipo_producto_id: {tipo_producto_id}")
            
            # Actualizar solo el campo tipo_producto_id
            response = (
                self.supabase.from_('cotizaciones')
                .update({'tipo_producto_id': tipo_producto_id})
                .eq('id', cotizacion_id)
                .execute()
            )
            
            if not response.data:
                print("No se recibió respuesta al actualizar la cotización")
                return False
                
            print(f"Cotización actualizada exitosamente: {response.data[0]}")
            print(f"Nuevo tipo_producto_id: {response.data[0].get('tipo_producto_id')}")
            return True
            
        except Exception as e:
            print(f"Error al corregir tipo_producto_id: {str(e)}")
            traceback.print_exc()
            return False

    def guardar_cotizacion(self, cotizacion: Cotizacion) -> Tuple[bool, str]:
        """
        Guarda una cotización en la base de datos.
        Si la cotización ya existe, la actualiza.
        Si no existe, crea una nueva.
        """
        try:
            if not cotizacion:
                return False, "No se proporcionó una cotización válida"

            print("\n=== DEBUG GUARDAR COTIZACIÓN ===")
            print("Datos de cotización:")
            if hasattr(cotizacion, 'cliente_id'):
                print(f"  Cliente: {cotizacion.cliente_id}")

            # Verificar si existe una referencia temporal en el session state
            if hasattr(st.session_state, 'referencia_temporal') and st.session_state.referencia_temporal:
                print("Creando nueva referencia...")
                try:
                    # Crear la referencia temporal
                    referencia_temporal = st.session_state.referencia_temporal
                    referencia_creada = self.crear_referencia(referencia_temporal)
                    
                    if referencia_creada:
                        # Actualizar el ID de la referencia en la cotización
                        cotizacion.referencia_cliente_id = referencia_creada.id
                    else:
                        return False, "No se pudo crear la referencia. Por favor, verifica los datos."
                except ValueError as ve:
                    error_msg = str(ve)
                    print(f"Error de validación capturado: {error_msg}")
                    # Personalizar el mensaje de error para el usuario
                    if "Ya existe una referencia con la misma descripción" in error_msg:
                        descripcion = st.session_state.referencia_temporal.descripcion
                        return False, f"⚠️ No se puede guardar la cotización porque ya existe una referencia con la descripción: '{descripcion}'\n\nPor favor, utiliza una descripción diferente para esta referencia."
                    return False, f"Error de validación: {error_msg}"

            # Verificar si la cotización ya existe
            cotizacion_existente = self.get_cotizacion_by_referencia(cotizacion.referencia_cliente_id)
            
            # Preparar los datos para guardar
            data = {
                'referencia_cliente_id': cotizacion.referencia_cliente_id,
                'fecha_creacion': datetime.now().isoformat() if not cotizacion_existente else None,
                'fecha_actualizacion': datetime.now().isoformat(),
                'material_id': cotizacion.material_id,
                'acabado_id': cotizacion.acabado_id,
                'num_tintas': cotizacion.num_tintas,
                'num_paquetes_rollos': cotizacion.num_paquetes_rollos,
                'numero_cotizacion': cotizacion.numero_cotizacion or self.obtener_proximo_consecutivo(),
                'es_manga': cotizacion.es_manga,
                'tipo_grafado_id': cotizacion.tipo_grafado_id,
                'tipo_pegue_id': cotizacion.tipo_pegue_id,
                'estado_id': cotizacion.estado_id,
                'tipo_producto_id': cotizacion.tipo_producto_id,
                'valor_troquel': cotizacion.valor_troquel,
                'valor_plancha_separado': cotizacion.valor_plancha_separado,
                'planchas_x_separado': cotizacion.planchas_x_separado,
                'existe_troquel': cotizacion.existe_troquel,
                'numero_pistas': cotizacion.numero_pistas,
                'colores_tinta': cotizacion.colores_tinta,
                'es_recotizacion': cotizacion.es_recotizacion,
                'ancho': cotizacion.ancho,
                'avance': cotizacion.avance,
                'observaciones': cotizacion.observaciones
            }
            
            # Eliminar campos None y generar identificador
            data = {k: v for k, v in data.items() if v is not None}
            
            # Si tiene identificador y ya existe, usarlo, de lo contrario generar uno nuevo
            if cotizacion_existente and cotizacion_existente.identificador:
                data['identificador'] = cotizacion_existente.identificador
            else:
                # Se generará automáticamente en crear_cotizacion o actualizar_cotizacion
                pass

            if cotizacion_existente:
                # Actualizar la cotización existente
                resultado = self.actualizar_cotizacion(cotizacion_existente.id, data)
                cotizacion.id = cotizacion_existente.id
                mensaje = "✅ Cotización actualizada exitosamente"
            else:
                # Crear una nueva cotización
                resultado = self.crear_cotizacion(data)
                if resultado:
                    cotizacion.id = resultado['id']
                    mensaje = "✅ Cotización creada exitosamente"
                else:
                    return False, "❌ Error al crear la cotización. Por favor, verifica los datos e intenta nuevamente."

            # Guardar las escalas si existen
            if cotizacion.escalas:
                if not self.guardar_cotizacion_escalas(cotizacion.id, cotizacion.escalas):
                    return False, "⚠️ La cotización se guardó, pero hubo un error al guardar las escalas. Por favor, verifica los datos de las escalas."

            # Limpiar la referencia temporal del session state
            if hasattr(st.session_state, 'referencia_temporal'):
                del st.session_state.referencia_temporal

            return True, mensaje

        except Exception as e:
            print(f"Error al guardar la cotización: {str(e)}")
            traceback.print_exc()
            # Convertir el error técnico en un mensaje amigable para el usuario
            mensaje_error = "❌ No se pudo guardar la cotización. "
            if "duplicate key value violates unique constraint" in str(e):
                mensaje_error = "⚠️ Ya existe una referencia con la misma descripción. Por favor, utiliza una descripción diferente."
            else:
                mensaje_error += "Ocurrió un error inesperado. Por favor, verifica los datos e intenta nuevamente."
            return False, mensaje_error 