from supabase import create_client, Client
from typing import List, Optional, Dict, Any, Tuple
from model_classes.cotizacion_model import Cotizacion, Material, Acabado, Cliente, Comercial, Escala, ReferenciaCliente, TipoProducto, PrecioEscala, TipoGrafado, EstadoCotizacion, MotivoRechazo, FormaPago
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
        Ahora también reintenta si operation_func devuelve None.
        
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
                result = operation_func() # Store result
                if result is None: # Check if the operation returned None
                    # Treat None result like a retryable error
                    last_error = ConnectionError(f"{operation_name} returned None on attempt {attempt + 1}")
                    if attempt < max_retries - 1:
                        print(f"Operation {operation_name} returned None (intento {attempt + 1}/{max_retries}).")
                        print(f"Reintentando en {delay} segundos...")
                        time.sleep(delay)
                        delay *= 2
                        continue # Go to next attempt
                    else:
                        # If it's the last attempt and still None, loop will end, error raised below
                        print(f"Operation {operation_name} returned None after {max_retries} attempts.")
                else:
                    return result # Return the valid result (not None)
                    
            except httpx.RemoteProtocolError as e:
                last_error = e
                if attempt < max_retries - 1:
                    print(f"Error de conexión en {operation_name} (intento {attempt + 1}/{max_retries}): {str(e)}")
                    # Log more details if available (optional)
                    # print(f"Detalles del error: {e.__dict__}") 
                    print(f"Reintentando en {delay} segundos...")
                    time.sleep(delay)
                    delay *= 2  # Backoff exponencial
                continue # Go to next attempt
            except Exception as e:
                # For other non-retryable errors, raise immediately
                print(f"Error no recuperable en {operation_name} (intento {attempt + 1}): {type(e).__name__} - {e}")
                raise e

        # If loop finishes without returning, it means all retries failed
        error_msg = f"Error persistente en {operation_name} después de {max_retries} intentos: {str(last_error)}"
        print(error_msg)
        # Raise the last recorded error (either ConnectionError for None or httpx error)
        if last_error:
            raise last_error
        else:
            # Should not happen if loop finished, but as a fallback
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
                         'tipo_producto_id', 'etiquetas_por_rollo', 'forma_pago_id']
        campos_numericos = ['valor_troquel', 'valor_plancha_separado', 'avance', 'altura_grafado']
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

    def obtener_proximo_consecutivo(self, tipo_documento: str = "COTIZACION") -> Optional[int]:
        """
        Obtiene el próximo número consecutivo para un tipo de documento.
        Para COTIZACION, usa la función RPC dedicada get_next_cotizacion_sequence_value.
        
        Args:
            tipo_documento (str): Tipo de documento.
        
        Returns:
            Optional[int]: El próximo número consecutivo o None si hay error.
        """
        try:
            # Validar el tipo de documento
            if not tipo_documento or not isinstance(tipo_documento, str):
                raise ValueError("Tipo de documento inválido")
            
            print(f"\n=== OBTENIENDO CONSECUTIVO PARA {tipo_documento} ===")
            
            # Usar la nueva RPC específica para cotizaciones
            if tipo_documento.upper() == "COTIZACION":
                print("Usando RPC get_next_cotizacion_sequence_value...")
                response = self.supabase.rpc('get_next_cotizacion_sequence_value').execute()
            else:
                # Mantener la lógica original para otros tipos de documento (si existen)
                # O podrías crear RPCs específicas para ellos también
                print(f"Usando RPC obtener_proximo_consecutivo para tipo: {tipo_documento}...")
            response = self.supabase.rpc(
                'obtener_proximo_consecutivo', 
                {'p_tipo_documento': tipo_documento}
            ).execute()
            
            # Procesar respuesta
            if response is None or not hasattr(response, 'data'):
                 print(f"Error: La respuesta de Supabase RPC fue inválida para {tipo_documento}.")
                 return None

            consecutivo = response.data
            print(f"Consecutivo obtenido de RPC: {consecutivo}")
            
            # Validar que el consecutivo sea un número entero positivo o None
            if consecutivo is not None and (not isinstance(consecutivo, int) or consecutivo <= 0):
                print(f"Advertencia: Consecutivo inválido generado por RPC: {consecutivo}. Revisar función RPC.")
                return None # Devolver None si la RPC da un valor inválido
            elif consecutivo is None:
                 print(f"Error: La función RPC no devolvió un consecutivo para {tipo_documento}.")
                 return None
            
            print(f"=== CONSECUTIVO GENERADO: {consecutivo} ===\n")
            return consecutivo
        
        except Exception as e:
            # Registrar el error para depuración
            error_msg = f"Error general al obtener consecutivo para {tipo_documento}: {str(e)}"
            print(error_msg)
            logging.error(error_msg)
            # Devolver None en caso de error general
            return None

    def get_next_numero_cotizacion(self) -> int:
        """Obtiene el siguiente número de cotización disponible."""
        try:
            # Llamamos directamente a la función RPC
            response = self.supabase.rpc('get_next_cotizacion_sequence_value').execute()
            
            if not hasattr(response, 'data'):
                print("Error: API response missing 'data' attribute in get_next_numero_cotizacion")
                return None
                
            if response.data is not None:
                return response.data
            else:
                print("Error: Función RPC retornó None")
                return None
            
        except Exception as e:
            print(f"Error general al obtener el siguiente número de cotización: {str(e)}")
            return None

    def crear_cotizacion(self, datos_cotizacion):
        """Crea una nueva cotización."""
        def _operation():
            # 1. Preparar datos iniciales (sin identificador ni número de cotización predefinido)
            print("\\nPreparando datos iniciales para la inserción...")
            # Eliminar campos que asignará la BD o que se usarán después
            datos_cotizacion.pop('identificador', None)
            datos_cotizacion.pop('numero_cotizacion', None)

            # Convertir valores Decimal a float para JSON si es necesario
            for key in ['valor_troquel', 'valor_plancha_separado']:
                if key in datos_cotizacion and datos_cotizacion[key] is not None:
                    try:
                        datos_cotizacion[key] = float(datos_cotizacion[key])
                    except (TypeError, ValueError):
                        print(f"Error convirtiendo {key} a float")
                        datos_cotizacion[key] = 0.0
            
            # Asegurarse que forma_pago_id esté presente como None si no se proporcionó
            if 'forma_pago_id' not in datos_cotizacion or datos_cotizacion['forma_pago_id'] is None:
                print("Estableciendo forma_pago_id por defecto a 1 (antes de RPC)")
                datos_cotizacion['forma_pago_id'] = 1 # O el default que corresponda
            
            
            print("\\nDatos para la llamada RPC inicial:")
            # Incluir altura_grafado si existe y no es None
            if 'altura_grafado' in datos_cotizacion and datos_cotizacion['altura_grafado'] is not None:
                print(f"  altura_grafado: {datos_cotizacion['altura_grafado']}")
            
            for k, v in datos_cotizacion.items():
                # Evitar imprimir altura_grafado dos veces si ya se imprimió arriba
                if k != 'altura_grafado' or ('altura_grafado' in datos_cotizacion and datos_cotizacion['altura_grafado'] is None):
                     print(f"  {k}: {v}")
            
            # 2. Llamar a la función RPC para crear la cotización (la BD asigna numero_cotizacion)
            try:
                print("\\nLlamando a la función RPC crear_cotizacion...")
                result = self.supabase.rpc('crear_cotizacion', {'datos': datos_cotizacion}).execute()

                if not result or not hasattr(result, 'data'):
                    print("Error: No se recibió respuesta válida del servidor")
                    raise ValueError("No se recibió respuesta válida del servidor al crear cotización")

                print(f"Respuesta RPC recibida: {result.data}")
                
                # Extraer los datos de la cotización creada
                cotizacion_creada_data = None
                if isinstance(result.data, list) and result.data:
                    cotizacion_creada_data = result.data[0]
                elif isinstance(result.data, dict): # Si la RPC devuelve un solo objeto
                     cotizacion_creada_data = result.data

                if not cotizacion_creada_data or 'id' not in cotizacion_creada_data or 'numero_cotizacion' not in cotizacion_creada_data:
                    print("Error: La respuesta RPC no contiene ID o numero_cotizacion válido")
                    print(f"Datos recibidos: {cotizacion_creada_data}")
                    raise ValueError("Respuesta inválida de RPC crear_cotizacion")
                
                cotizacion_id = cotizacion_creada_data['id']
                numero_cotizacion_final = cotizacion_creada_data['numero_cotizacion']
                print(f"Cotización creada con ID: {cotizacion_id}, Número Consecutivo Final: {numero_cotizacion_final}")

            except Exception as e:
                print(f"Error durante la creación inicial de cotización vía RPC: {e}")
                print(f"Tipo de error: {type(e)}")
                print(f"Detalles del error: {str(e)}")
                raise e # Re-lanzar para que _retry_operation pueda manejarlo si es necesario

            # 3. Obtener datos necesarios para generar el identificador (ya que no estaban en cotizacion_creada_data)
            print("\\nObteniendo datos adicionales para generar el identificador final...")
            try:
                tipo_producto = "MANGA" if datos_cotizacion.get('es_manga') else "ETIQUETA"
                material_code = self.get_material_code(datos_cotizacion.get('material_id'))
                acabado_code = self.get_acabado_code(datos_cotizacion.get('acabado_id')) if not datos_cotizacion.get('es_manga') else ""
                
                referencia = self.get_referencia_cliente(datos_cotizacion.get('referencia_cliente_id'))
                if not referencia:
                    # Esto no debería pasar si la inserción fue exitosa, pero por seguridad
                    raise ValueError(f"No se encontró la referencia {datos_cotizacion.get('referencia_cliente_id')} después de crear cotización")
                
                cliente = referencia.cliente
                if not cliente:
                     raise ValueError(f"No se encontró el cliente para la referencia {referencia.id} después de crear cotización")

                cliente_nombre = cliente.nombre
                referencia_descripcion = referencia.descripcion

            except Exception as e:
                 print(f"Error obteniendo datos para el identificador post-inserción: {e}")
                 # Considerar si fallar aquí o intentar continuar sin identificador
                 raise ValueError(f"Fallo al obtener datos para identificador: {e}")

            # 4. Generar el identificador AHORA con el número final
            print(f"\\nGenerando identificador con número final {numero_cotizacion_final}...")
            identificador_final = ""
            try:
                identificador_final = self._generar_identificador(
                    tipo_producto=tipo_producto,
                    material_code=material_code,
                    ancho=datos_cotizacion.get('ancho', 0),
                    avance=datos_cotizacion.get('avance', 0),
                    num_pistas=datos_cotizacion.get('numero_pistas', 1),
                    num_tintas=datos_cotizacion.get('num_tintas', 0),
                    acabado_code=acabado_code,
                    num_paquetes_rollos=datos_cotizacion.get('num_paquetes_rollos', 0),
                    cliente=cliente_nombre,
                    referencia=referencia_descripcion,
                    numero_cotizacion=numero_cotizacion_final # Usar el número final de la BD
                )
                print(f"Identificador final generado: {identificador_final}")
            except Exception as e:
                print(f"Error generando identificador final: {e}")
                # Decidir qué hacer: continuar sin identificador o fallar?
                # Por ahora, continuamos pero registramos el error. El campo será "" o el valor por defecto.
                st.warning(f"No se pudo generar el identificador para la cotización {cotizacion_id}. Error: {e}")


            # 5. Actualizar la cotización con el identificador generado
            if identificador_final:
                print(f"\\nActualizando cotización {cotizacion_id} con el identificador final...")
                try:
                    update_response = self.supabase.from_('cotizaciones') \
                        .update({'identificador': identificador_final}) \
                        .eq('id', cotizacion_id) \
                        .execute()

                    if not update_response.data:
                        print(f"Error: No se pudo actualizar la cotización {cotizacion_id} con el identificador.")
                        # Considerar si esto es un error crítico o solo una advertencia
                        st.warning(f"Cotización {cotizacion_id} creada, pero falló la actualización del identificador.")
                    else:
                        print("Identificador actualizado correctamente.")
                        # Actualizar el diccionario de datos devuelto para que incluya el identificador
                        cotizacion_creada_data['identificador'] = identificador_final

                except Exception as e:
                    print(f"Error actualizando identificador para cotización {cotizacion_id}: {e}")
                    st.warning(f"Cotización {cotizacion_id} creada, pero falló la actualización del identificador. Error: {e}")
            
            # 6. Devolver los datos de la cotización creada (incluyendo id y numero_cotizacion_final)
            return cotizacion_creada_data

        try:
            # Usar _retry_operation para manejar posibles reintentos en la operación completa
            return self._retry_operation("crear cotización y generar ID", _operation)
        except Exception as e:
            print(f"Error final en el proceso de crear cotización: {str(e)}")
            traceback.print_exc()
            return None # O devolver una estructura de error

    def actualizar_cotizacion(self, cotizacion_id: int, datos_cotizacion: Dict) -> Tuple[bool, str]:
        """
        Actualiza una cotización existente
        
        Args:
            cotizacion_id (int): ID de la cotización a actualizar
            datos_cotizacion (Dict): Diccionario con los datos a actualizar
            
        Returns:
            Tuple[bool, str]: (éxito, mensaje)
        """
        try:
            print(f"\n=== ACTUALIZANDO COTIZACIÓN {cotizacion_id} ===")
            print("Datos a actualizar:", datos_cotizacion)
            
            # Validar estado y motivo de rechazo
            estado_id = datos_cotizacion.get('estado_id')
            id_motivo_rechazo = datos_cotizacion.get('id_motivo_rechazo')
            
            if estado_id == 3 and id_motivo_rechazo is None:
                return False, "❌ Se requiere un motivo de rechazo cuando el estado es 'Rechazado'"
            
            # Limpiar datos antes de actualizar
            datos_limpios = self._limpiar_datos(datos_cotizacion)
            print("\nDatos limpios a actualizar:")
            for k, v in datos_limpios.items():
                print(f"  {k}: {v}")
            
            # Actualizar la cotización
            response = self.supabase.from_('cotizaciones') \
                .update(datos_limpios) \
                .eq('id', cotizacion_id) \
                .execute()
            
            if not response.data:
                return False, "❌ No se pudo actualizar la cotización"
            
            print(f"Cotización actualizada exitosamente: {response.data[0]}")
            return True, "✅ Cotización actualizada exitosamente"
            
        except Exception as e:
            error_msg = str(e)
            print(f"Error al actualizar cotización: {error_msg}")
            traceback.print_exc()
            
            # Manejar errores específicos
            if "id_motivo_rechazo no puede ser NULL cuando estado_id es 3" in error_msg:
                return False, "❌ Se requiere un motivo de rechazo cuando el estado es 'Rechazado'"
            
            # Manejar posible error de FK para forma_pago_id si se implementa constraint
            if 'fk_cotizaciones_forma_pago' in error_msg:
                return False, f"❌ Forma de pago inválida seleccionada."
            
            return False, f"❌ Error al actualizar la cotización: {error_msg}"

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

    def get_clientes_by_comercial(self, comercial_id: str) -> List[Cliente]:
        """
        Obtiene la lista de clientes asociados a un comercial específico.
        
        Args:
            comercial_id (str): ID del comercial (UUID)
            
        Returns:
            List[Cliente]: Lista de clientes asociados al comercial
        """
        def _operation():
            try:
                # Primero obtenemos las referencias de cliente asociadas al comercial
                referencias = self.supabase.table('referencias_cliente')\
                    .select('cliente_id')\
                    .eq('id_usuario', comercial_id)\
                    .execute()

                if not referencias.data:
                    return []

                # Extraemos los IDs únicos de clientes
                cliente_ids = list(set(ref['cliente_id'] for ref in referencias.data))

                # Obtenemos los detalles de los clientes
                clientes = self.supabase.table('clientes')\
                    .select('*')\
                    .in_('id', cliente_ids)\
                    .execute()

                return [Cliente(
                    id=cliente['id'],
                    nombre=cliente['nombre'],
                    codigo=cliente.get('codigo'),
                    persona_contacto=cliente.get('persona_contacto'),
                    correo_electronico=cliente.get('correo_electronico'),
                    telefono=cliente.get('telefono'),
                    creado_en=datetime.fromisoformat(cliente['creado_en']) if cliente.get('creado_en') else None,
                    actualizado_en=datetime.fromisoformat(cliente['actualizado_en']) if cliente.get('actualizado_en') else None
                ) for cliente in clientes.data] if clientes.data else []

            except Exception as e:
                print(f"Error obteniendo clientes por comercial: {str(e)}")
                traceback.print_exc()
                return []

        return self._retry_operation(
            operation_name="get_clientes_by_comercial",
            operation_func=_operation
        )

    def get_materiales(self) -> List[Material]:
        """Obtiene todos los materiales disponibles usando RPC."""
        def _operation():
            print("\n=== DEBUG: Llamando RPC get_all_materials ===")
            response = self.supabase.rpc('get_all_materials').execute()
            
            if response is None:
                 print("ERROR: La respuesta de Supabase RPC fue None en get_materiales.")
                 raise ConnectionError("Supabase RPC devolvió None en get_materiales")
            
            if not response.data:
                logging.warning("No se encontraron materiales (vía RPC)")
                return []
            
            materiales = []
            # La respuesta RPC ya debería tener la estructura deseada (incluyendo adhesivo_tipo)
            for item in response.data:
                # Crear el objeto Material directamente desde el item devuelto por RPC
                try:
                    materiales.append(Material(**item)) 
                except TypeError as te:
                    print(f"Error creando objeto Material desde RPC data: {te}")
                    print(f"Datos del item problemático: {item}")
                    # Opcional: continuar con los siguientes o lanzar error
                    continue 
                    
            print(f"Materiales obtenidos vía RPC: {len(materiales)}")
            return materiales

        try:
            # Usar _retry_operation con la función RPC
            return self._retry_operation("obtener materiales (RPC)", _operation)
        except ConnectionError as ce:
             print(f"Error de conexión persistente en get_materiales (RPC): {ce}")
             raise # Re-lanzar para que la app lo maneje si es necesario
        except Exception as e:
            logging.error(f"Error al obtener materiales (RPC): {str(e)}")
            traceback.print_exc()
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
        """Obtiene todos los acabados disponibles usando RPC."""
        def _operation():
            print("\n=== DEBUG: Llamando RPC get_all_acabados ===")
            response = self.supabase.rpc('get_all_acabados').execute()
            
            if response is None:
                 print("ERROR: La respuesta de Supabase RPC fue None en get_acabados.")
                 raise ConnectionError("Supabase RPC devolvió None en get_acabados")
            
            if not response.data:
                logging.warning("No se encontraron acabados (vía RPC)")
                return []
                
            # Crear objetos Acabado directamente desde la respuesta RPC
            acabados = []
            for item in response.data:
                 try:
                     acabados.append(Acabado(**item))
                 except TypeError as te:
                    print(f"Error creando objeto Acabado desde RPC data: {te}")
                    print(f"Datos del item problemático: {item}")
                    continue
                    
            print(f"Acabados obtenidos vía RPC: {len(acabados)}")        
            return acabados
            
        try:
            # Usar _retry_operation con la función RPC
            return self._retry_operation("obtener acabados (RPC)", _operation)
        except ConnectionError as ce:
             print(f"Error de conexión persistente en get_acabados (RPC): {ce}")
             raise
        except Exception as e:
            logging.error(f"Error al obtener acabados (RPC): {str(e)}")
            traceback.print_exc()
            raise

    def get_acabado(self, acabado_id: int) -> Optional[Acabado]:
        """Obtiene un acabado específico por su ID."""
        try:
            # Validar que acabado_id no sea None y sea un entero válido
            if acabado_id is None or not isinstance(acabado_id, int):
                print(f"ID de acabado inválido: {acabado_id}")
                return None
                
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
        """Obtiene todos los tipos de producto disponibles usando RPC."""
        def _operation():
            print("\n=== DEBUG: Llamando RPC get_all_tipos_producto ===")
            response = self.supabase.rpc('get_all_tipos_producto').execute()

            if response is None:
                 print("ERROR: La respuesta de Supabase RPC fue None en get_tipos_producto.")
                 raise ConnectionError("Supabase RPC devolvió None en get_tipos_producto")
            
            if not response.data:
                print("No se encontraron tipos de producto (vía RPC)")
                return []
            
            tipos_producto = []
            for item in response.data:
                try:
                    tipos_producto.append(TipoProducto(**item))
                except TypeError as te:
                    print(f"Error creando objeto TipoProducto desde RPC data: {te}")
                    print(f"Datos del item problemático: {item}")
                    continue
            
            print(f"Se encontraron {len(tipos_producto)} tipos de producto (vía RPC)")
            return tipos_producto
            
        try:
             # Usar _retry_operation con la función RPC
            return self._retry_operation("obtener tipos producto (RPC)", _operation)
        except ConnectionError as ce:
             print(f"Error de conexión persistente en get_tipos_producto (RPC): {ce}")
             raise # Re-lanzar para que la app lo maneje si es necesario
        except Exception as e:
            print(f"Error al obtener tipos de producto (RPC): {e}")
            traceback.print_exc()
            raise # O return [] si prefieres no detener la app

    def get_tipo_producto(self, tipo_producto_id: int) -> Optional[TipoProducto]:
        """Obtiene un tipo de producto específico por su ID."""
        # TODO: Considerar cambiar a RPC si las consultas SELECT directas siguen fallando.
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
        """Obtiene los tipos de grafado disponibles para mangas usando RPC."""
        # TODO: Cambiar a RPC si las consultas SELECT directas fallan. <- Cambiado a RPC
        def _operation():
            print("\n=== DEBUG: Llamando RPC get_tipos_grafado_manga ===") # Cambiado nombre RPC
            response = self.supabase.rpc('get_tipos_grafado_manga').execute() # Cambiado nombre RPC

            if response is None:
                 print("ERROR: La respuesta de Supabase RPC fue None en get_tipos_grafado.")
                 raise ConnectionError("Supabase RPC devolvió None en get_tipos_grafado")
            
            if not response.data:
                print("No se encontraron tipos de grafado para mangas (vía RPC)") # Mensaje actualizado
                return []
            
            tipos_grafado = []
            for item in response.data:
                try:
                    # Usar from_dict si existe y maneja la conversión
                    if hasattr(TipoGrafado, 'from_dict'):
                        tipos_grafado.append(TipoGrafado.from_dict(item))
                    else:
                        # Si no hay from_dict, intentar instanciar directamente
                        tipos_grafado.append(TipoGrafado(**item))
                except TypeError as te:
                    print(f"Error creando objeto TipoGrafado desde RPC data: {te}")
                    print(f"Datos del item problemático: {item}")
                    continue # Saltar este item y continuar con los siguientes
                except Exception as e:
                     print(f"Error inesperado creando TipoGrafado desde RPC data: {e}")
                     print(f"Datos del item problemático: {item}")
                     continue

            print(f"Se encontraron {len(tipos_grafado)} tipos de grafado para mangas (vía RPC)") # Mensaje actualizado
            return tipos_grafado
            
        try:
             # Usar _retry_operation con la función RPC
            return self._retry_operation("obtener tipos grafado manga (RPC)", _operation) # Nombre operación actualizado
        except ConnectionError as ce:
             print(f"Error de conexión persistente en get_tipos_grafado (RPC): {ce}")
             raise # Re-lanzar para que la app lo maneje si es necesario
        except Exception as e:
            print(f"Error al obtener tipos de grafado para mangas (RPC): {e}") # Mensaje actualizado
            traceback.print_exc()
            raise # O return [] si prefieres no detener la app

    def get_tipos_grafado_id_by_name(self, grafado_name: str) -> Optional[int]:
        """Obtiene el ID de un tipo de grafado por su nombre."""
        if not grafado_name:
            return None
        try:
            # TODO: Considerar usar RPC si las SELECT directas fallan persistentemente.
            response = self.supabase.from_('tipos_grafado') \
                .select('id') \
                .eq('nombre', grafado_name) \
                .limit(1) \
                .execute()
            
            if response.data and len(response.data) > 0:
                return response.data[0]['id']
            else:
                print(f"Advertencia: No se encontró ID para el tipo de grafado con nombre: '{grafado_name}'")
                return None
        except Exception as e:
            print(f"Error al obtener ID de tipo de grafado por nombre '{grafado_name}': {e}")
            traceback.print_exc()
            return None

    def get_perfil(self, user_id: str) -> Optional[Dict]:
        """Obtiene el perfil del usuario con su rol (incluyendo el nombre del rol)"""
        try:
            # Hacemos join con la tabla de roles para obtener el nombre del rol
            response = self.supabase.from_('perfiles') \
                .select('*, rol:roles(nombre)') \
                .eq('id', user_id) \
                .single() \
                .execute()
            if response and response.data:
                perfil = response.data
                # Extraer el nombre del rol del join
                if 'rol' in perfil and perfil['rol'] and 'nombre' in perfil['rol']:
                    perfil['rol_nombre'] = perfil['rol']['nombre']
                return perfil
            return None
        except Exception as e:
            print(f"Error obteniendo perfil: {str(e)}")
            return None

    def get_perfiles_by_role(self, role_name: str) -> List[Dict]:
        """Obtiene los perfiles (id, nombre) asociados a un rol específico."""
        try:
            print(f"\n=== INICIO GET_PERFILES_BY_ROLE para rol: {role_name} ===")
            print(f"Intentando ejecutar RPC 'get_perfiles_by_role' con parámetro: {role_name}")
            
            # Obtener el token JWT actual para debugging
            auth = self.supabase.auth.get_session()
            print(f"Estado de autenticación: {'Autenticado' if auth else 'No autenticado'}")
            if auth:
                print(f"Role claim en JWT: {auth.user.role if auth.user else 'No role claim'}")
            
            response = self.supabase.rpc(
                'get_perfiles_by_role',
                {'p_rol_nombre': role_name}
            ).execute()

            # Log detallado de la respuesta
            print(f"Respuesta RPC completa: {response}")
            print(f"Tipo de response: {type(response)}")
            print(f"Atributos de response: {dir(response)}")
            if hasattr(response, 'error'):
                print(f"Error en response: {response.error}")
            print(f"Tipo de response.data: {type(response.data)}")
            print(f"Contenido de response.data: {response.data}")

            if response.data:
                print(f"Perfiles encontrados para rol '{role_name}': {len(response.data)}")
                print("=== FIN GET_PERFILES_BY_ROLE (con datos) ===\n")
                # Asegurarse de que la respuesta sea una lista de diccionarios
                if isinstance(response.data, list) and all(isinstance(item, dict) for item in response.data):
                    return response.data
                else:
                    print(f"ERROR: Formato inesperado en response.data: {type(response.data)}")
                    return []
            else:
                # Podría ser que no haya usuarios con ese rol, lo cual no es un error
                print(f"No se encontraron perfiles para el rol '{role_name}'.")
                print("=== FIN GET_PERFILES_BY_ROLE (sin datos) ===\n")
                return []

        except Exception as e:
            print(f"Error general en get_perfiles_by_role: {e}")
            print(f"Traceback completo:")
            traceback.print_exc()
            print("=== FIN GET_PERFILES_BY_ROLE (con error) ===\n")
            return []

    def get_comercial_default(self) -> Optional[str]:
        """Obtiene el ID del comercial por defecto (primero de la lista).
        NOTA: Esta función puede necesitar ser revisada o eliminada si ya no aplica
        el concepto de 'comercial por defecto' con la estructura de perfiles/roles."""
        try:
            # Intenta obtener el primer perfil con rol 'comercial'
            response = self.supabase.from_('perfiles') \
                .select('id, rol:roles!inner(nombre)') \
                .eq('rol.nombre', 'comercial') \
                .limit(1) \
                .execute()

            if response.data and len(response.data) > 0:
                return response.data[0]['id']
            
            # Fallback si no se encuentra un comercial
            print("Advertencia: No se encontró un perfil con rol 'comercial'. Usando fallback.")
            # Considera retornar None o manejar este caso de forma diferente
            return 'faf071b9-a885-4d8a-b65e-6a3b3785334a' # Manteniendo fallback anterior, pero es cuestionable
        except Exception as e:
            print(f"Error al obtener comercial por defecto: {e}")
            return 'faf071b9-a885-4d8a-b65e-6a3b3785334a' # ID de comercial por defecto

    def get_clientes(self) -> List[Cliente]:
        """Obtiene todos los clientes disponibles usando RPC."""
        def _operation():
            print("\n=== DEBUG: Llamando RPC get_all_clientes ===")
            response = self.supabase.rpc('get_all_clientes').execute()
            
            if response is None:
                 print("ERROR: La respuesta de Supabase RPC fue None en get_clientes.")
                 raise ConnectionError("Supabase RPC devolvió None en get_clientes")
            
            if not response.data:
                print("No se encontraron clientes (vía RPC)")
                return []
            
            clientes = []
            for item in response.data:
                 try:
                     clientes.append(Cliente(**item))
                 except TypeError as te:
                    print(f"Error creando objeto Cliente desde RPC data: {te}")
                    print(f"Datos del item problemático: {item}")
                    continue
                    
            print(f"Se encontraron {len(clientes)} clientes (vía RPC)")        
            return clientes

        try:
            # Usar _retry_operation con la función RPC
            return self._retry_operation("obtener clientes (RPC)", _operation)
        except ConnectionError as ce:
             print(f"Error de conexión persistente en get_clientes (RPC): {ce}")
             raise
        except Exception as e:
            print(f"Error al obtener clientes (RPC): {str(e)}")
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
        """Obtiene las referencias de un cliente que pertenecen al comercial actual.
        Debido a las políticas RLS, solo se retornarán las referencias donde id_comercial = auth.uid()"""
        try:
            # La consulta ya está protegida por RLS, solo retornará las referencias del comercial actual
            response = self.supabase.table('referencias_cliente').select(
                '*'
            ).eq('cliente_id', cliente_id).execute()
            
            referencias = []
            if response.data: # Asegurarse que hay datos antes de iterar
                for data in response.data:
                    try:
                        referencia = ReferenciaCliente(
                            id=data['id'],
                            cliente_id=data['cliente_id'],
                            descripcion=data['descripcion'],
                            creado_en=data['creado_en'],
                            actualizado_en=data['actualizado_en'],
                            id_usuario=data.get('id_usuario'), # Usar id_usuario
                            tiene_cotizacion=data.get('tiene_cotizacion', False)
                        )
                        referencias.append(referencia)
                    except Exception as e:
                        print(f"Error creando objeto ReferenciaCliente desde datos: {data}. Error: {e}")
                        continue # Saltar esta referencia si hay error
            return referencias
        except Exception as e:
            print(f"Error general al obtener referencias del cliente: {e}")
            return []

    def get_referencia_cliente(self, referencia_id: int) -> Optional[ReferenciaCliente]:
        """Obtiene una referencia de cliente por su ID usando una función RPC dedicada."""
        try:
            print(f"\n--- DEBUG: get_referencia_cliente (RPC) para ID: {referencia_id} ---")
            
            # Llamar a la nueva función RPC
            response = self.supabase.rpc(
                'get_referencia_cliente_details', 
                {'p_referencia_id': referencia_id}
            ).execute()
            
            print(f"Respuesta RPC: {response.data}")
            
            # La RPC devuelve una lista con un diccionario si encuentra la referencia
            if response.data:
                data = response.data[0]
                
                # Crear objeto Cliente si existe
                cliente_obj = None
                if data.get('cliente_id'):
                    cliente_obj = Cliente(
                        id=data['cliente_id'],
                        nombre=data['cliente_nombre'],
                        codigo=data['cliente_codigo'],
                        persona_contacto=data['cliente_persona_contacto'],
                        correo_electronico=data['cliente_correo_electronico'],
                        telefono=data['cliente_telefono']
                        # creado_en y actualizado_en no vienen de la RPC, podrían añadirse si es necesario
                    )
                print(f"Objeto Cliente creado: {cliente_obj}")
                
                # Crear diccionario de perfil si existe
                perfil_simple = None
                if data.get('perfil_id'):
                    perfil_simple = {
                        'id': data['perfil_id'],
                        'nombre': data['perfil_nombre'],
                        'email': data['perfil_email'],
                        'celular': data['perfil_celular'] 
                        # rol_id y otros campos pueden añadirse si se necesitan
                    }
                print(f"Datos del perfil obtenidos: {perfil_simple}")

                # Crear objeto ReferenciaCliente con relaciones
                referencia_obj = ReferenciaCliente(
                    id=data['ref_id'],
                    cliente_id=data['ref_cliente_id'],
                    descripcion=data['ref_descripcion'],
                    creado_en=data['ref_creado_en'],
                    actualizado_en=data['ref_actualizado_en'],
                    id_usuario=data['ref_id_usuario'], 
                    # tiene_cotizacion no viene de la RPC, se podría añadir a la función SQL si es necesario
                    # tiene_cotizacion=False, 
                    cliente=cliente_obj, 
                    perfil=perfil_simple 
                )
                print(f"Objeto ReferenciaCliente final: {referencia_obj}")
                print("--- FIN DEBUG: get_referencia_cliente (RPC) ---")
                return referencia_obj
                
            print("No se encontraron datos para la referencia vía RPC.")
            print("--- FIN DEBUG: get_referencia_cliente (RPC) ---")
            return None
        except Exception as e:
            print(f"Error al obtener referencia del cliente (RPC): {e}")
            traceback.print_exc()
            return None
    

    def crear_referencia_y_cotizacion(self, datos_referencia: dict, datos_cotizacion: dict) -> Optional[Tuple[int, int]]:
        """
        Crea una nueva referencia y su cotización asociada en una transacción
        Retorna: (referencia_id, cotizacion_id) o None si hay error
        """
        try:
            # Iniciar transacción
            # Nota: Supabase no soporta transacciones directamente, así que manejamos
            # la lógica de rollback manualmente
            
            # 1. Crear la referencia
            response_ref = self.supabase.table('referencias_cliente')\
                .insert(datos_referencia)\
                .execute()
            
            if not response_ref.data:
                raise Exception("Error al crear la referencia")
            
            referencia_id = response_ref.data[0]['id']
            
            # 2. Actualizar datos_cotizacion con el ID de la referencia
            datos_cotizacion['referencia_cliente_id'] = referencia_id
            
            # 3. Crear la cotización
            response_cot = self.supabase.table('cotizaciones')\
                .insert(datos_cotizacion)\
                .execute()
            
            if not response_cot.data:
                # Si falla la cotización, intentamos eliminar la referencia
                self.supabase.table('referencias_cliente')\
                    .delete()\
                    .eq('id', referencia_id)\
                    .execute()
                raise Exception("Error al crear la cotización")
            
            cotizacion_id = response_cot.data[0]['id']
            
            return referencia_id, cotizacion_id
            
        except Exception as e:
            print(f"Error en crear_referencia_y_cotizacion: {str(e)}")
            return None
    
    def crear_referencia(self, referencia: ReferenciaCliente) -> Optional[ReferenciaCliente]:
        """Crea una nueva referencia de cliente. 
        Cualquier comercial autenticado puede crear referencias para cualquier cliente."""
        def _operation():
            # Validar datos requeridos
            if not referencia.cliente_id or not referencia.descripcion:
                print("Error: cliente_id y descripcion son requeridos")
                return None

            # Usar el id_usuario del objeto ReferenciaCliente si se proporciona,
            # o intentar obtener el del usuario actual si no.
            if not referencia.id_usuario:
                print("Advertencia: id_usuario no proporcionado en la referencia. Se intentará usar el usuario actual.")
                # Es posible que necesites obtener el ID del usuario actual aquí si no viene en el objeto 'referencia'
                # Ejemplo: current_user_id = self.supabase.auth.get_user().user.id (esto depende de tu flujo de autenticación)
                # Por ahora, asumiremos que si no viene, es un error o se manejará antes.
                # Si es obligatorio, descomenta y ajusta:
                # print("Error: id_usuario es requerido para crear la referencia")
                # return None
                user_id_to_use = None # Define cómo obtenerlo si no viene
                if user_id_to_use is None:
                     print("Error crítico: No se pudo determinar el id_usuario para la referencia.")
                return None
            else:
                user_id_to_use = referencia.id_usuario

            # Verificar que el usuario (id_usuario) tenga rol de comercial
            try:
                print(f"\n=== Verificando perfil para usuario ID: {user_id_to_use} ===")
                # Usar la función que obtiene perfil por ID
                perfil = self.get_perfil(user_id_to_use)

                if not perfil:
                    error_msg = f"❌ No se pudo verificar el perfil del usuario con ID: {user_id_to_use}"
                    print(error_msg)
                    raise ValueError(error_msg)

                # Asumiendo que get_perfil ahora devuelve rol_nombre
                if perfil.get('rol_nombre') != 'comercial':
                    error_msg = f"❌ Se requiere rol de comercial. Rol del usuario {user_id_to_use}: {perfil.get('rol_nombre')}"
                    print(error_msg)
                    raise ValueError(error_msg)

                print(f"✅ Usuario {user_id_to_use} verificado como comercial: {perfil.get('nombre')}")
            except Exception as e:
                error_msg = f"❌ Error al verificar rol de usuario {user_id_to_use}: {str(e)}"
                print(error_msg)
                raise ValueError(error_msg)

            # Preparar datos básicos
            data = {
                'cliente_id': referencia.cliente_id,
                'descripcion': referencia.descripcion.strip(),
                'id_usuario': user_id_to_use
            }

            print("\nDatos a insertar en referencias_cliente:")
            for k, v in data.items():
                print(f"  {k}: {v} (Tipo: {type(v)}) ")

            # Verificar si ya existe una referencia con la misma descripción para este cliente
            existing = self.supabase.rpc(
                'check_referencia_exists',
                {
                    'p_cliente_id': referencia.cliente_id,
                    'p_descripcion': data['descripcion']
                }
            ).execute()

            if existing.data:
                # La RPC devuelve directamente un booleano
                exists = existing.data
                if exists:
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

            # Insertar la referencia usando RPC (asegúrate que la RPC solo use id_usuario)
            response = self.supabase.rpc(
                'crear_referencia_cliente',
                {
                    'p_id_usuario': data['id_usuario'], # Pasar id_usuario
                    'p_cliente_id': data['cliente_id'],
                    'p_descripcion': data['descripcion']
                    # No pasar id_comercial
                }
            ).execute()
            
            if response.data:
                # La RPC 'crear_referencia_cliente' debería devolver el ID
                # O podrías necesitar obtener la referencia completa recién creada
                referencia_id_creada = response.data # Ajusta según lo que devuelva la RPC
                print(f"Referencia creada ID (respuesta RPC): {referencia_id_creada}")
                # Si la RPC devuelve el ID o la fila completa, extraer el ID para buscar la referencia
                actual_id = referencia_id_creada['id'] if isinstance(referencia_id_creada, dict) else referencia_id_creada
                return self.get_referencia_cliente(actual_id)
            return None

        try:
            return self._retry_operation("crear referencia", _operation)
        except postgrest.exceptions.APIError as e:
            if e.code == '42501':  # Código de error para violación de RLS
                error_msg = "❌ No tienes permiso para crear referencias. Verifica que estés autenticado como comercial."
                print(error_msg)
                raise ValueError(error_msg)
            print(f"Error al crear referencia (APIError): {e}")
            traceback.print_exc()
            raise e
        except ValueError as ve:
            # Re-lanzar ValueError para mostrar mensajes específicos (ej: rol incorrecto, duplicado)
            raise ve
        except Exception as e:
            error_msg = f"❌ Error inesperado al crear la referencia: {str(e)}"
            print(error_msg)
            traceback.print_exc()
            raise e

    def get_datos_completos_cotizacion(self, cotizacion_id: int) -> dict:
        """
        Obtiene todos los datos necesarios para generar el PDF de una cotización.
        Debido a las políticas RLS, solo se podrá obtener si la cotización está vinculada
        a una referencia cuyo id_usuario es el usuario actual.
        
        Args:
            cotizacion_id (int): ID de la cotización a obtener. Es obligatorio.
            
        Returns:
            dict: Diccionario con todos los datos de la cotización o None si hay error
            
        Raises:
            ValueError: Si cotizacion_id es None o no es un entero válido
        """
        try:
            print("\n=== DEBUG GET_DATOS_COMPLETOS_COTIZACION (Refactorizado) ===")
            print(f"Obteniendo datos para cotización ID: {cotizacion_id} usando obtener_cotizacion")

            # Llamar a la función optimizada para obtener el objeto Cotizacion
            cotizacion = self.obtener_cotizacion(cotizacion_id)

            if not cotizacion:
                print("No se encontró la cotización o no tienes permiso para verla (desde obtener_cotizacion)")
                print("=== FIN GET_DATOS_COMPLETOS_COTIZACION (sin datos) ===\n")
                return None
            
            print("\nCotización obtenida, transformando a diccionario para PDF...")

            # Extraer datos del objeto Cotizacion y sus relaciones
            referencia = cotizacion.referencia_cliente
            cliente = referencia.cliente if referencia else None
            perfil_comercial = referencia.perfil if referencia else None # Perfil es un dict
            material = cotizacion.material
            acabado = cotizacion.acabado
            tipo_producto = cotizacion.tipo_producto
            # Remove redundant fetch, rely on cotizacion.forma_pago from obtener_cotizacion
            # forma_pago = self.get_forma_pago(cotizacion.forma_pago_id) if cotizacion.forma_pago_id else None
            
            # Obtener los valores de material, acabado y troquel de la tabla de cálculos
            calculos = self.get_calculos_escala_cotizacion(cotizacion_id)
            valor_material = calculos.get('valor_material', 0) if calculos else 0
            valor_acabado = calculos.get('valor_acabado', 0) if calculos else 0
            valor_troquel = calculos.get('valor_troquel', 0) if calculos else 0
            
            # Construir el diccionario de cliente
            cliente_dict = {}
            if cliente:
                cliente_dict = {
                    'id': cliente.id,
                    'nombre': cliente.nombre,
                    'codigo': cliente.codigo,
                    'persona_contacto': cliente.persona_contacto,
                    'correo_electronico': cliente.correo_electronico,
                    'telefono': cliente.telefono
                }

            # Preparar el diccionario de datos final
            datos = {
                'id': cotizacion.id,
                'consecutivo': cotizacion.numero_cotizacion,
                'nombre_cliente': cliente.nombre if cliente else None,
                'descripcion': referencia.descripcion if referencia else None,
                'material': material.__dict__ if material else {},
                'acabado': acabado.__dict__ if acabado else {},
                'num_tintas': cotizacion.num_tintas,
                'num_rollos': cotizacion.num_paquetes_rollos,
                'es_manga': cotizacion.es_manga,
                'tipo_grafado': cotizacion.tipo_grafado_id, # Mantener como ID
                'valor_plancha_separado': cotizacion.valor_plancha_separado or 0,
                'cliente': cliente_dict,
                'comercial': perfil_comercial, # Ya es un dict
                'identificador': cotizacion.identificador,
                'tipo_producto': tipo_producto.__dict__ if tipo_producto else {},
                # Agregar los valores para el PDF de materiales
                'valor_material': valor_material,
                'valor_acabado': valor_acabado,
                'valor_troquel': valor_troquel,
                # Información adicional de impresión
                'ancho': calculos.get('ancho', 0) if calculos else 0,
                'avance': calculos.get('avance', 0) if calculos else 0,
                'numero_pistas': calculos.get('numero_pistas', 0) if calculos else 0,
                'desperdicio_total': calculos.get('desperdicio_total', 0) if calculos else 0,
                # Use cotizacion.forma_pago (the object) directly
                'forma_pago_desc': cotizacion.forma_pago.descripcion if cotizacion.forma_pago and cotizacion.forma_pago.descripcion else "No especificada"
            }
            
            print("\nDatos preparados para el PDF (desde objeto Cotizacion):")
            # Imprimir solo algunos campos para no llenar el log
            print(f"  ID: {datos.get('id')}")
            print(f"  Consecutivo: {datos.get('consecutivo')}")
            print(f"  Cliente: {datos.get('nombre_cliente')}")
            print(f"  Referencia: {datos.get('descripcion')}")
            print(f"  Identificador: {datos.get('identificador')}")
            print(f"  Comercial: {datos.get('comercial', {}).get('nombre')}")
            print(f"  Valor Material: {datos.get('valor_material')}")
            print(f"  Valor Acabado: {datos.get('valor_acabado')}")
            print(f"  Valor Troquel: {datos.get('valor_troquel')}")
            print(f"  Forma de Pago: {datos.get('forma_pago_desc')}") # Imprimir forma de pago

            # Procesar las escalas desde el objeto cotizacion.escalas
            datos['resultados'] = [] # Inicializar siempre la lista
            if cotizacion.escalas:
                print(f"\nProcesando {len(cotizacion.escalas)} escalas...")
                for escala in cotizacion.escalas:
                    resultado = {
                        'escala': escala.escala,
                        'valor_unidad': escala.valor_unidad,
                        'metros': escala.metros,
                        'tiempo_horas': escala.tiempo_horas,
                        'montaje': escala.montaje,
                        'mo_y_maq': escala.mo_y_maq,
                        'tintas': escala.tintas,
                        'papel_lam': escala.papel_lam,
                        'desperdicio': escala.desperdicio_total # Asegurarse que este es el campo correcto
                    }
                    print(f"  Escala procesada: {resultado['escala']}, Valor unidad: {resultado['valor_unidad']}")
                    datos['resultados'].append(resultado)
                print(f"Total de resultados añadidos: {len(datos['resultados'])}")
            else:
                print("\nNo se encontraron escalas en el objeto Cotizacion")
            
            print("=== FIN GET_DATOS_COMPLETOS_COTIZACION (Refactorizado) ===\n")
            return datos
            
        except ValueError as ve:
            # Propagar errores de validación específicos
            print(f"Error en get_datos_completos_cotizacion (Refactorizado): {str(ve)}")
            traceback.print_exc()
            raise ve
        except Exception as e:
            print(f"Error en get_datos_completos_cotizacion (Refactorizado): {e}")
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
                escalas.append(escala)
            
            print(f"Se encontraron {len(escalas)} escalas")
            print("=== FIN GET_COTIZACION_ESCALAS ===\n")
            return escalas
            
        except Exception as e:
            print(f"Error obteniendo escalas de cotización: {e}")
            traceback.print_exc()
            return []

    def get_precios_escala(self, escala_id: int) -> List[PrecioEscala]:
        """Obtiene todos los precios asociados a una escala.
        NOTA: Actualmente devuelve una lista vacía porque la tabla 'precios_escala' no existe.
        La información principal de la escala (ej: valor_unidad) se carga desde 'cotizacion_escalas'."""
        # try:
        #     response = self.supabase.from_('precios_escala').select('*').eq('escala_id', escala_id).execute()
            
        #     if not response.data:
        #         return []
            
        #     return [PrecioEscala(**precio_data) for precio_data in response.data]
            
        # except Exception as e:
        #     print(f"Error obteniendo precios de escala: {e}")
        #     traceback.print_exc()
        #     return []
        print(f"INFO: La función get_precios_escala para escala_id {escala_id} devuelve lista vacía (tabla precios_escala no existe).")
        return [] # Devuelve lista vacía para evitar error

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

    def guardar_cotizacion(self, cotizacion: Cotizacion, datos_cotizacion: Dict = None) -> Tuple[bool, str]:
        """Guarda o actualiza una cotización y sus datos relacionados"""
        try:
            print("\n=== INICIO GUARDAR_COTIZACION ===")
            print(f"Cotización a guardar: {cotizacion}")
            print(f"Datos adicionales: {datos_cotizacion}")
            
            # Verificar si es una actualización o una nueva cotización
            es_actualizacion = cotizacion.id is not None
            
            # Preparar datos básicos de la cotización
            datos_cotizacion_base = {
                'referencia_cliente_id': cotizacion.referencia_cliente_id,
                'material_id': cotizacion.material_id,
                'acabado_id': cotizacion.acabado_id,
                'num_tintas': cotizacion.num_tintas,
                'num_paquetes_rollos': cotizacion.num_paquetes_rollos,
                'es_manga': cotizacion.es_manga,
                'tipo_grafado_id': cotizacion.tipo_grafado_id,
                'valor_troquel': float(cotizacion.valor_troquel) if cotizacion.valor_troquel else None,
                'valor_plancha_separado': float(cotizacion.valor_plancha_separado) if cotizacion.valor_plancha_separado else None,
                'planchas_x_separado': cotizacion.planchas_x_separado,
                'existe_troquel': cotizacion.existe_troquel,
                'numero_pistas': cotizacion.numero_pistas,
                'tipo_producto_id': cotizacion.tipo_producto_id,
                'ancho': cotizacion.ancho,
                'avance': cotizacion.avance,
                'identificador': cotizacion.identificador,
                'forma_pago_id': cotizacion.forma_pago_id,
                'altura_grafado': cotizacion.altura_grafado
            }
            
            # Si es una actualización
            if es_actualizacion:
                print(f"Actualizando cotización existente con ID: {cotizacion.id}")
                response = self.supabase.from_('cotizaciones') \
                    .update(datos_cotizacion_base) \
                    .eq('id', cotizacion.id) \
                    .execute()
                
                mensaje = "✅ Cotización actualizada exitosamente"
            else:
                # Si es una nueva cotización
                print("Creando nueva cotización")
                response = self.supabase.from_('cotizaciones') \
                    .insert(datos_cotizacion_base) \
                    .execute()
                
                if response.data:
                    cotizacion.id = response.data[0]['id']
                mensaje = "✅ Cotización creada exitosamente"
            
            if not response.data:
                return False, "⚠️ No se pudo guardar la cotización en la base de datos"
            
            # Guardar las escalas si existen
            if cotizacion.escalas:
                if not self.guardar_cotizacion_escalas(cotizacion.id, cotizacion.escalas):
                    return False, "⚠️ La cotización se guardó, pero hubo un error al guardar las escalas"
            
            # Guardar los cálculos de escala si hay datos adicionales
            if datos_cotizacion and 'datos_cotizacion' in datos_cotizacion:
                datos = datos_cotizacion['datos_cotizacion']
                calculos_escala = {
                    'cotizacion_id': cotizacion.id,
                    'valor_material': datos.get('valor_material'),
                    'valor_plancha': datos.get('valor_plancha'),
                    'valor_troquel': datos.get('valor_troquel'),
                    'rentabilidad': datos.get('rentabilidad'),
                    'valor_acabado': datos.get('valor_acabado'),
                    'avance': datos.get('avance'),
                    'ancho': datos.get('ancho'),
                    'existe_troquel': datos.get('existe_troquel'),
                    'planchas_x_separado': datos.get('planchas_x_separado'),
                    'num_tintas': datos.get('num_tintas'),
                    'numero_pistas': datos.get('numero_pistas'),
                    'num_paquetes_rollos': datos.get('num_paquetes_rollos'),
                    'tipo_producto_id': datos.get('tipo_producto_id'),
                    'tipo_grafado_id': datos.get('tipo_grafado_id'),
                    'unidad_z_dientes': datos.get('unidad_z_dientes')
                }
                
                # Actualizar o insertar los cálculos de escala
                if not self.guardar_calculos_escala(cotizacion.id, calculos_escala):
                    return False, "⚠️ La cotización se guardó, pero hubo un error al guardar los cálculos de escala"
            
            print("=== FIN GUARDAR_COTIZACION ===\n")
            return True, mensaje
            
        except Exception as e:
            print(f"Error al guardar la cotización: {str(e)}")
            traceback.print_exc()
            return False, f"❌ Error al guardar la cotización: {str(e)}"

    def guardar_calculos_escala(self, cotizacion_id: int, 
                                valor_material: float, valor_plancha: float, valor_troquel: float, rentabilidad: float, 
                                avance: float, ancho: float, existe_troquel: bool, planchas_x_separado: bool, 
                                num_tintas: int, numero_pistas: int, num_paquetes_rollos: int, 
                                tipo_producto_id: int, tipo_grafado_id: Optional[int], valor_acabado: float, 
                                unidad_z_dientes: float) -> bool:
        """Guarda o actualiza los parámetros de cálculo de escala para una cotización usando RPC."""
        if not cotizacion_id:
            print("Error: cotizacion_id es requerido para guardar cálculos de escala.")
            return False

        # Prepare the dictionary with parameters for the RPC function
        # Ensure keys match the SQL function parameter names (e.g., p_cotizacion_id)
        rpc_params = {
            'p_cotizacion_id': cotizacion_id,
            'p_valor_material': valor_material,
            'p_valor_plancha': valor_plancha,
            'p_valor_troquel': valor_troquel,
            'p_rentabilidad': rentabilidad,
            'p_avance': avance,
            'p_ancho': ancho,
            'p_existe_troquel': existe_troquel,
            'p_planchas_x_separado': planchas_x_separado,
            'p_num_tintas': num_tintas,
            'p_numero_pistas': numero_pistas,
            'p_num_paquetes_rollos': num_paquetes_rollos,
            'p_tipo_producto_id': tipo_producto_id,
            'p_tipo_grafado_id': tipo_grafado_id, # Pass None if applicable
            'p_valor_acabado': valor_acabado,
            'p_unidad_z_dientes': unidad_z_dientes
        }

        try:
            print(f"\nLlamando a RPC 'upsert_calculos_escala' para cotizacion_id: {cotizacion_id}")
            print(f"Parámetros RPC: {rpc_params}")

            response = self.supabase.rpc('upsert_calculos_escala', rpc_params).execute()

            # Check if the RPC call was successful and returned data
            # --- MODIFICACIÓN: Handle direct dictionary in response.data ---
            success_data = None
            if hasattr(response, 'data'):
                if isinstance(response.data, list) and len(response.data) > 0:
                    # Handle case where data is a list containing the row
                    success_data = response.data[0]
                elif isinstance(response.data, dict) and response.data: # Check if it's a non-empty dictionary
                    # Handle case where data is the row dictionary directly
                    success_data = response.data

            if success_data is not None:
                print(f"RPC upsert_calculos_escala exitoso. Fila afectada: {success_data}")
                return True
            # --- FIN MODIFICACIÓN ---
            elif hasattr(response, 'error') and response.error:
                 # Handle potential errors returned by the RPC call itself (e.g., network or SQL error raised in RPC)
                 print(f"Error en la llamada RPC upsert_calculos_escala: {response.error}")
                 # Attempt to extract details if possible
                 error_details = getattr(response.error, 'details', None)
                 error_message = getattr(response.error, 'message', str(response.error))
                 print(f"  Message: {error_message}")
                 if error_details: print(f"  Details: {error_details}")
                 return False
            elif hasattr(response, 'data') and (response.data is None or (isinstance(response.data, list) and len(response.data) == 0)):
                # Case where the RPC executed but returned no rows (might happen if ON CONFLICT condition wasn't met correctly, or other logic paths)
                print(f"RPC upsert_calculos_escala ejecutado pero no devolvió filas. Respuesta: {response.data}")
                # Consider this potentially problematic, returning False
                return False
            else:
                # Catch-all for other unexpected response structures
                print(f"Respuesta inesperada de RPC upsert_calculos_escala: {response}")
                return False
            # --- FIN MODIFICACIÓN ---

        except postgrest.exceptions.APIError as api_error:
            # Catch specific Postgrest errors, including our custom permission denied
            if api_error.code == '42501' and 'permission_denied' in api_error.message:
                 print(f"Error de permisos (RLS/RPC check) al guardar cálculos escala: {api_error.message}")
                 # You might want to raise this or handle it specifically in the calling function
                 # For now, return False
            else:
                 print(f"Error de API (Postgrest) al guardar cálculos escala: {api_error}")
                 traceback.print_exc()
            return False
        except Exception as e:
            # Catch any other unexpected errors
            print(f"Error fatal al guardar cálculos de escala (RPC) para cotizacion_id {cotizacion_id}: {str(e)}")
            traceback.print_exc()
            return False

    def get_cotizacion_por_referencia(self, referencia_id: int) -> Optional[Cotizacion]:
        """Obtiene la cotización asociada a una referencia"""
        try:
            print(f"\n=== INICIO GET_COTIZACION_POR_REFERENCIA para referencia {referencia_id} ===")
            
            # Obtener la cotización más reciente para esta referencia
            response = self.supabase.from_('cotizaciones') \
                .select('*') \
                .eq('referencia_cliente_id', referencia_id) \
                .order('fecha_creacion', desc=True) \
                .limit(1) \
                .execute()
            
            if not response.data:
                print("No se encontró cotización para esta referencia")
                return None
            
            cotizacion_data = response.data[0]
            
            # Obtener datos relacionados
            referencia = self.get_referencia_cliente(referencia_id)
            material = self.get_material(cotizacion_data['material_id']) if cotizacion_data.get('material_id') else None
            acabado = self.get_acabado(cotizacion_data['acabado_id']) if cotizacion_data.get('acabado_id') else None
            tipo_producto = self.get_tipo_producto(cotizacion_data['tipo_producto_id']) if cotizacion_data.get('tipo_producto_id') else None
            forma_pago = self.get_forma_pago(cotizacion_data['forma_pago_id']) if cotizacion_data.get('forma_pago_id') else None
            
            # Crear objeto Cotizacion con todos los datos
            cotizacion = Cotizacion(
                id=cotizacion_data['id'],
                referencia_cliente_id=referencia_id,
                material_id=cotizacion_data.get('material_id'),
                acabado_id=cotizacion_data.get('acabado_id'),
                num_tintas=cotizacion_data.get('num_tintas'),
                num_paquetes_rollos=cotizacion_data.get('num_paquetes_rollos'),
                numero_cotizacion=cotizacion_data.get('numero_cotizacion'),
                es_manga=cotizacion_data.get('es_manga', False),
                tipo_grafado_id=cotizacion_data.get('tipo_grafado_id'),
                valor_troquel=cotizacion_data.get('valor_troquel'),
                valor_plancha_separado=cotizacion_data.get('valor_plancha_separado'),
                planchas_x_separado=cotizacion_data.get('planchas_x_separado', False),
                existe_troquel=cotizacion_data.get('existe_troquel', False),
                numero_pistas=cotizacion_data.get('numero_pistas', 1),
                tipo_producto_id=cotizacion_data.get('tipo_producto_id'),
                ancho=cotizacion_data.get('ancho', 0.0),
                avance=cotizacion_data.get('avance', 0.0),
                fecha_creacion=cotizacion_data.get('fecha_creacion'),
                identificador=cotizacion_data.get('identificador'),
                estado_id=cotizacion_data.get('estado_id'),
                id_motivo_rechazo=cotizacion_data.get('id_motivo_rechazo'),
                es_recotizacion=cotizacion_data.get('es_recotizacion', False),
                altura_grafado=cotizacion_data.get('altura_grafado'), # NUEVO: Añadir altura_grafado
                # Relaciones
                referencia_cliente=referencia,
                material=material,
                acabado=acabado,
                tipo_producto=tipo_producto,
                forma_pago=forma_pago
            )
            
            # Obtener y asignar las escalas
            cotizacion.escalas = self.get_cotizacion_escalas(cotizacion.id)
            
            print("=== FIN GET_COTIZACION_POR_REFERENCIA ===\n")
            return cotizacion
            
        except Exception as e:
            print(f"Error al obtener cotización por referencia: {e}")
            traceback.print_exc()
            return None

    def get_calculos_escala_cotizacion(self, cotizacion_id: int) -> Optional[Dict]:
        """Obtiene los cálculos de escala asociados a una cotización"""
        try:
            print(f"\n=== INICIO GET_CALCULOS_ESCALA_COTIZACION para cotización {cotizacion_id} ===")
            
            response = self.supabase.from_('calculos_escala_cotizacion') \
                .select('*') \
                .eq('cotizacion_id', cotizacion_id) \
                .execute()
            
            if not response.data:
                print("No se encontraron cálculos de escala para esta cotización")
                return None
            
            calculos = response.data[0]
            print(f"Cálculos encontrados: {calculos}")
            print("=== FIN GET_CALCULOS_ESCALA_COTIZACION ===\n")
            return calculos
            
        except Exception as e:
            print(f"Error al obtener cálculos de escala: {e}")
            traceback.print_exc()
            return None 

    def obtener_cotizacion(self, cotizacion_id: int) -> Optional[Cotizacion]:
        """
        Obtiene una cotización específica por su ID respetando las políticas RLS:
        - Los administradores pueden ver cualquier cotización
        - Los comerciales solo pueden ver cotizaciones vinculadas a referencias donde son propietarios
        
        Args:
            cotizacion_id (int): ID de la cotización a obtener. Es obligatorio.
            
        Returns:
            Optional[Cotizacion]: Objeto Cotizacion con sus relaciones o None si no se encuentra
                                o no se tiene permiso para acceder
                                
        Raises:
            ValueError: Si cotizacion_id es None o no es un entero válido
        """
        # Validar que cotizacion_id sea un entero válido
        if cotizacion_id is None:
            raise ValueError("El ID de cotización es obligatorio y no puede ser None")
            
        try:
            cotizacion_id = int(cotizacion_id)
        except (TypeError, ValueError):
            raise ValueError(f"El ID de cotización debe ser un entero válido, se recibió: {cotizacion_id} ({type(cotizacion_id)})")

        def _operation():
            print(f"\n=== INICIO OBTENER_COTIZACION para ID: {cotizacion_id} ===")
            
            # DEBUG: Verificar si hay un usuario autenticado y su rol
            try:
                # Obtener información del usuario actual
                print("=== DEBUG: Verificando usuario autenticado ===")
                user_info = self.supabase.auth.get_user()
                
                if not user_info or not hasattr(user_info, 'user') or not user_info.user:
                    print("⚠️ ERROR: No hay usuario autenticado. La RLS bloqueará el acceso.")
                    print("=== FIN OBTENER_COTIZACION (sin autenticación) ===\n")
                    # Lanzar un error específico para no reintentar en este caso
                    raise ValueError("NO_AUTH: Se requiere iniciar sesión para acceder a los datos de la cotización")
                
                current_user_id = user_info.user.id
                print(f"✅ Usuario autenticado: ID={current_user_id}, Email={user_info.user.email}")
                
                # Obtener perfil y rol del usuario
                print("=== DEBUG: Verificando perfil y rol del usuario ===")
                perfil = self.get_perfil(current_user_id)
                
                if not perfil:
                    print("⚠️ ERROR: El usuario autenticado no tiene perfil. La RLS bloqueará el acceso.")
                    raise ValueError("NO_PROFILE: El usuario autenticado no tiene un perfil asociado")
                
                rol = perfil.get('rol_nombre')
                print(f"✅ Rol del usuario: {rol}")
                
                # Verificar si el usuario es administrador (puede ver cualquier cotización)
                es_admin = rol == 'administrador'
                print(f"¿Es administrador? {'Sí' if es_admin else 'No'}")
                
                # Si no es administrador, verificar si es comercial
                if not es_admin:
                    if rol != 'comercial':
                        print(f"⚠️ ERROR: El usuario tiene rol '{rol}', que no tiene permisos para cotizaciones.")
                        raise ValueError(f"INVALID_ROLE: Se requiere rol 'administrador' o 'comercial', pero el usuario tiene rol '{rol}'")
                    
                    # DEBUG: Verificar si la cotización está asociada a una referencia propiedad del comercial
                    print("=== DEBUG: Verificando propiedad de la referencia ===")
                    # Primero obtener la referencia_cliente_id de la cotización
                    ref_response = self.supabase.from_('cotizaciones') \
                        .select('referencia_cliente_id') \
                        .eq('id', cotizacion_id) \
                        .execute()
                    
                    if not ref_response.data or len(ref_response.data) == 0:
                        print(f"⚠️ ERROR: No se encontró la cotización con ID {cotizacion_id}")
                        return None
                    
                    referencia_id = ref_response.data[0].get('referencia_cliente_id')
                    print(f"ID de la referencia asociada: {referencia_id}")
                    
                    # Verificar si el usuario actual es propietario de la referencia
                    ref_owner_response = self.supabase.from_('referencias_cliente') \
                        .select('id_usuario') \
                        .eq('id', referencia_id) \
                        .execute()
                    
                    if not ref_owner_response.data or len(ref_owner_response.data) == 0:
                        print(f"⚠️ ERROR: No se encontró la referencia con ID {referencia_id}")
                        return None
                    
                    ref_owner_id = ref_owner_response.data[0].get('id_usuario')
                    print(f"Propietario de la referencia: {ref_owner_id}")
                    print(f"Usuario actual: {current_user_id}")
                    
                    if ref_owner_id != current_user_id:
                        print("⚠️ ERROR: El usuario no es propietario de la referencia. La RLS bloqueará el acceso.")
                        raise ValueError("NO_PERMISSION: No tienes permiso para acceder a esta cotización porque no eres propietario de la referencia asociada")
                    else:
                        print("✅ El usuario es propietario de la referencia. Tiene permiso para ver la cotización.")
            
            except ValueError as ve:
                # Propagar errores de validación específicos
                print(f"⚠️ ERROR de validación: {str(ve)}")
                raise ve
            except Exception as e:
                print(f"❌ ERROR durante verificación de permisos: {e}")
                traceback.print_exc()
                # Continuar con la consulta aunque haya error en la verificación
            
            # Intentamos obtener la cotización mediante select normal
            try:
                # Obtener la cotización básica (esto respetará RLS automáticamente)
                print("=== DEBUG: Intentando obtener cotización ===")
                response = self.supabase.from_('cotizaciones') \
                    .select('*') \
                    .eq('id', cotizacion_id) \
                    .execute()
                    
                # Si no se encuentra, puede ser por falta de permisos o porque no existe
                if not response.data or len(response.data) == 0:
                    print(f"⚠️ ERROR: No se encontró la cotización con ID {cotizacion_id} o no tienes permiso para verla")
                    return None
                    
                cotizacion_data = response.data[0]
                print(f"✅ Cotización básica encontrada: {cotizacion_data['id']}")
                
                # Obtener relaciones
                referencia = self.get_referencia_cliente(cotizacion_data['referencia_cliente_id']) if cotizacion_data.get('referencia_cliente_id') else None
                
                material = self.get_material(cotizacion_data['material_id']) if cotizacion_data.get('material_id') else None
                
                acabado = self.get_acabado(cotizacion_data['acabado_id']) if cotizacion_data.get('acabado_id') else None
                
                tipo_producto = self.get_tipo_producto(cotizacion_data['tipo_producto_id']) if cotizacion_data.get('tipo_producto_id') else None
                
                forma_pago = self.get_forma_pago(cotizacion_data['forma_pago_id']) if cotizacion_data.get('forma_pago_id') else None
                
                # Crear objeto Cotizacion con todos sus datos
                cotizacion = Cotizacion(
                    id=cotizacion_data['id'],
                    referencia_cliente_id=cotizacion_data.get('referencia_cliente_id'),
                    material_id=cotizacion_data.get('material_id'),
                    acabado_id=cotizacion_data.get('acabado_id'),
                    num_tintas=cotizacion_data.get('num_tintas'),
                    num_paquetes_rollos=cotizacion_data.get('num_paquetes_rollos'),
                    numero_cotizacion=cotizacion_data.get('numero_cotizacion'),
                    es_manga=cotizacion_data.get('es_manga', False),
                    tipo_grafado_id=cotizacion_data.get('tipo_grafado_id'),
                    valor_troquel=cotizacion_data.get('valor_troquel'),
                    valor_plancha_separado=cotizacion_data.get('valor_plancha_separado'),
                    planchas_x_separado=cotizacion_data.get('planchas_x_separado', False),
                    existe_troquel=cotizacion_data.get('existe_troquel', False),
                    numero_pistas=cotizacion_data.get('numero_pistas', 1),
                    tipo_producto_id=cotizacion_data.get('tipo_producto_id'),
                    ancho=cotizacion_data.get('ancho', 0.0),
                    avance=cotizacion_data.get('avance', 0.0),
                    fecha_creacion=cotizacion_data.get('fecha_creacion'),
                    identificador=cotizacion_data.get('identificador'),
                    estado_id=cotizacion_data.get('estado_id'),
                    id_motivo_rechazo=cotizacion_data.get('id_motivo_rechazo'),
                    es_recotizacion=cotizacion_data.get('es_recotizacion', False),
                    altura_grafado=cotizacion_data.get('altura_grafado'), # NUEVO: Añadir altura_grafado
                    # Relaciones
                    referencia_cliente=referencia,
                    material=material,
                    acabado=acabado,
                    tipo_producto=tipo_producto,
                    forma_pago=forma_pago
                )
                
                # Obtener y asignar las escalas
                cotizacion.escalas = self.get_cotizacion_escalas(cotizacion.id)
                
                print(f"✅ Se encontró cotización completa. ID: {cotizacion.id}, Referencia: {referencia.descripcion if referencia else None}")
                print("=== FIN OBTENER_COTIZACION ===\n")
                return cotizacion
                
            except Exception as e:
                print(f"❌ ERROR al obtener cotización: {e}")
                traceback.print_exc()
                print("=== FIN OBTENER_COTIZACION (con error) ===\n")
                return None
        
        try:
            return self._retry_operation(f"obtener cotización {cotizacion_id}", _operation)
        except ValueError as ve:
            # Capturar errores de validación (NO_AUTH, NO_PROFILE, etc.)
            error_msg = str(ve)
            if error_msg.startswith("NO_AUTH:"):
                print(f"Error de autenticación: {error_msg}")
                # Puedes manejar el error de autenticación de manera específica
                # Por ejemplo, mostrar un mensaje al usuario
                return None
            elif error_msg.startswith(("NO_PROFILE:", "INVALID_ROLE:", "NO_PERMISSION:")):
                print(f"Error de permisos: {error_msg}")
                # Manejar otros errores de permisos
                return None
            # Propagar otros errores de ValueError
            raise ve
        except Exception as e:
            print(f"❌ ERROR general al obtener cotización: {e}")
            traceback.print_exc()
            return None

    def get_visible_cotizaciones_list(self) -> List[Dict]:
        """
        Obtiene la lista de cotizaciones visibles para el usuario actual (Admin o Comercial).
        Respeta las RLS y maneja datos faltantes (referencia, cliente) de forma más robusta.
        
        Returns:
            List[Dict]: Lista de diccionarios con datos básicos de las cotizaciones visibles.
                       Cada diccionario contiene: 'id', 'numero_cotizacion', 'referencia', 
                                              'cliente', 'fecha_creacion', 'estado_id'.
                       Retorna lista vacía si no hay cotizaciones o en caso de error.
        """
        def _operation():
            print("\n=== INICIO GET_VISIBLE_COTIZACIONES_LIST ===")
            
            # 1. Verificar usuario y rol
            current_user_id = None
            rol = None
            try:
                user_info = self.supabase.auth.get_user()
                if not user_info or not user_info.user:
                    print("⚠️ ERROR: No hay usuario autenticado.")
                    # No lanzar error aquí, RLS se encargará, pero la consulta podría devolver vacío.
                else:
                    current_user_id = user_info.user.id
                    print(f"Usuario autenticado: {current_user_id}")
                    perfil = self.get_perfil(current_user_id)
                    if perfil:
                        rol = perfil.get('rol_nombre')
                        print(f"Rol del usuario: {rol}")
                    else:
                        print(f"Advertencia: No se encontró perfil para el usuario {current_user_id}")
                        # Tratar como si no tuviera rol asignado (RLS bloqueará si es necesario)
                        
            except Exception as e:
                print(f"Error verificando usuario/rol: {e}")
                # Continuar; RLS se encargará de la seguridad.

            # 2. Construir la consulta SELECT basada en el rol (si se conoce)
            select_query = 'id, numero_cotizacion, fecha_creacion, estado_id'
            
            # Usamos LEFT JOIN para cliente para evitar filtrar si solo falta el nombre del cliente
            # El JOIN para referencia depende del rol para optimizar RLS
            if rol == 'administrador':
                # Admin puede ver todo, usamos LEFT JOIN para referencia y cliente
                select_query += ', referencias_cliente!left(descripcion, clientes!left(nombre))'
                print("Construyendo query para Administrador (LEFT JOINs)")
            elif rol == 'comercial':
                # Comercial: RLS filtra por sus referencias. Usamos INNER JOIN para referencia (optimización RLS)
                # y LEFT JOIN para cliente.
                select_query += ', referencias_cliente!inner(descripcion, clientes!left(nombre))'
                print("Construyendo query para Comercial (INNER JOIN ref, LEFT JOIN cliente)")
            else:
                # Rol desconocido o sin autenticar: RLS se aplicará. Usamos LEFT JOINs por si acaso.
                # Es probable que RLS bloquee la consulta si no es admin.
                select_query += ', referencias_cliente!left(descripcion, clientes!left(nombre))'
                print("Construyendo query para Rol desconocido/invitado (LEFT JOINs - RLS aplicará)")

            # 3. Ejecutar la consulta
            try:
                print(f"Ejecutando consulta: SELECT {select_query} FROM cotizaciones")
                response = self.supabase.from_('cotizaciones') \
                    .select(select_query) \
                    .order('fecha_creacion', desc=True) \
                    .execute()

                if not response.data:
                    print("No se encontraron cotizaciones visibles o la consulta falló.")
                    return []
                
                # 4. Procesar y formatear los resultados
                formatted_data = []
                print(f"Procesando {len(response.data)} cotizaciones recibidas...")
                for cotizacion in response.data:
                    try:
                        # Validar ID básico
                        cot_id = cotizacion.get('id')
                        if not isinstance(cot_id, int) or cot_id <= 0:
                             print(f"Saltando cotización con ID inválido: {cot_id}")
                             continue

                        ref_cliente_data = cotizacion.get('referencias_cliente', {}) or {} # Asegurar dict
                        cliente_data = ref_cliente_data.get('clientes', {}) or {} # Asegurar dict

                        formatted_data.append({
                            'id': cot_id,
                            'numero_cotizacion': str(cotizacion.get('numero_cotizacion', '')),
                            'referencia': ref_cliente_data.get('descripcion', 'N/A'), # Default si falta
                            'cliente': cliente_data.get('nombre', 'Sin Cliente'), # Default si falta
                            'fecha_creacion': cotizacion.get('fecha_creacion', ''),
                            'estado_id': cotizacion.get('estado_id')
                        })
                    except Exception as e_proc:
                        print(f"Error procesando cotización ID {cotizacion.get('id')}: {e_proc}")
                        continue # Saltar esta cotización si hay error al procesarla

                print(f"Se procesaron {len(formatted_data)} cotizaciones válidas.")
                print("=== FIN GET_VISIBLE_COTIZACIONES_LIST ===\n")
                return formatted_data

            except Exception as e_query:
                print(f"Error al ejecutar la consulta de cotizaciones: {e_query}")
                traceback.print_exc()
                return [] # Devolver lista vacía en caso de error de consulta

        # Usar retry_operation para la lógica completa
        try:
            # No usar retry si devuelve None (ya que None no es un resultado esperado aquí)
            # _retry_operation necesita ajustarse o no usarse si None es un caso de error específico.
            # Por ahora, llamaremos directamente a _operation. Si hay errores de conexión, deberían manejarse dentro.
             return _operation()
             # TODO: Revisar si _retry_operation debe usarse aquí y cómo manejar el caso de [] vs None
        except Exception as e:
            print(f"Error general en get_visible_cotizaciones_list: {str(e)}")
            traceback.print_exc()
            return []

    def get_estados_cotizacion(self) -> List[EstadoCotizacion]:
        """Obtiene todos los estados de cotización disponibles"""
        try:
            response = self.supabase.from_('estados_cotizacion').select('*').execute()
            
            if not response.data:
                return []
            
            return [EstadoCotizacion(**estado) for estado in response.data]
            
        except Exception as e:
            print(f"Error al obtener estados de cotización: {e}")
            traceback.print_exc()
            return []

    def get_motivos_rechazo(self) -> List[MotivoRechazo]:
        """Obtiene todos los motivos de rechazo disponibles"""
        try:
            response = self.supabase.from_('motivos_rechazo').select('*').execute()
            
            if not response.data:
                return []
            
            return [MotivoRechazo(**motivo) for motivo in response.data]
            
        except Exception as e:
            print(f"Error al obtener motivos de rechazo: {e}")
            traceback.print_exc()
            return []

    def actualizar_estado_cotizacion(self, cotizacion_id: int, estado_id: int, id_motivo_rechazo: Optional[int] = None) -> bool:
        """
        Actualiza el estado de una cotización y opcionalmente el motivo de rechazo.
        
        Args:
            cotizacion_id (int): ID de la cotización a actualizar
            estado_id (int): Nuevo estado_id
            id_motivo_rechazo (Optional[int]): ID del motivo de rechazo (requerido si estado_id es 3)
            
        Returns:
            bool: True si la actualización fue exitosa, False en caso contrario
        """
        try:
            print(f"\n=== ACTUALIZANDO ESTADO DE COTIZACIÓN {cotizacion_id} ===")
            print(f"Nuevo estado_id: {estado_id}")
            print(f"Motivo rechazo ID: {id_motivo_rechazo}")
            
            # Validar que si el estado es 3 (rechazado), se proporcione un motivo
            if estado_id == 3 and id_motivo_rechazo is None:
                print("Error: Se requiere un motivo de rechazo cuando el estado es 3 (rechazado)")
                return False
            
            # Preparar datos para actualización
            update_data = {
                'estado_id': estado_id,
                'id_motivo_rechazo': id_motivo_rechazo if estado_id == 3 else None,
                # Convertir datetime a string ISO 8601
                'actualizado_en': datetime.now().isoformat()  
            }
            
            # Actualizar la cotización
            response = self.supabase.from_('cotizaciones') \
                .update(update_data) \
                .eq('id', cotizacion_id) \
                .execute()
            
            if not response.data:
                print("No se recibió respuesta al actualizar el estado")
                return False
            
            print(f"Estado actualizado exitosamente: {response.data[0]}")
            return True
            
        except Exception as e:
            print(f"Error al actualizar estado de cotización: {str(e)}")
            traceback.print_exc()
            return False

    # --- NUEVO: Función para obtener descripción de forma de pago --- 
    def get_forma_pago_desc(self, forma_pago_id: Optional[int]) -> str:
        """Obtiene la descripción de una forma de pago por su ID."""
        if forma_pago_id is None:
            return "No especificada"
        forma_pago = self.get_forma_pago(forma_pago_id)
        return forma_pago.descripcion if forma_pago else "ID inválido"

    def get_formas_pago(self) -> List[FormaPago]:
        """Obtiene todas las formas de pago disponibles."""
        def _operation():
            print("\n=== DEBUG: Llamando RPC get_all_formas_pago ===") # Asumiendo RPC existe
            try:
                # Intentar con RPC primero (si existe)
                response = self.supabase.rpc('get_all_formas_pago').execute() 
            except Exception:
                 # Fallback a SELECT si RPC falla o no existe
                 print("Fallback a SELECT para formas_pago")
                 response = self.supabase.from_('formas_pago').select('*').order('id').execute()
            
            if response is None:
                 print("ERROR: La respuesta de Supabase fue None en get_formas_pago.")
                 raise ConnectionError("Supabase devolvió None en get_formas_pago")
            
            if not response.data:
                logging.warning("No se encontraron formas de pago")
                return []
                
            formas_pago = []
            for item in response.data:
                 try:
                     formas_pago.append(FormaPago(**item))
                 except TypeError as te:
                    print(f"Error creando objeto FormaPago desde data: {te}")
                    print(f"Datos del item problemático: {item}")
                    continue
                    
            print(f"Formas de pago obtenidas: {len(formas_pago)}")        
            return formas_pago
            
        try:
            return self._retry_operation("obtener formas de pago", _operation)
        except ConnectionError as ce:
             print(f"Error de conexión persistente en get_formas_pago: {ce}")
             raise
        except Exception as e:
            logging.error(f"Error al obtener formas de pago: {str(e)}")
            traceback.print_exc()
            raise
            
    def get_forma_pago(self, forma_pago_id: int) -> Optional[FormaPago]:
        """Obtiene una forma de pago específica por su ID."""
        if forma_pago_id is None:
            return None
        try:
            response = self.supabase.from_('formas_pago').select('*').eq('id', forma_pago_id).execute()
            
            if not response.data or len(response.data) == 0:
                print(f"No se encontró forma de pago con ID {forma_pago_id}")
                return None
            
            return FormaPago(**response.data[0])
            
        except Exception as e:
            print(f"Error al obtener forma de pago: {e}")
            traceback.print_exc()
            return None

    def get_referencias_by_cliente(self, cliente_id: int) -> List[ReferenciaCliente]:
        """Obtiene las referencias de un cliente"""
        try:
            response = self.supabase.table('referencias_cliente')\
                .select('*')\
                .eq('cliente_id', cliente_id)\
                .execute()
            return [ReferenciaCliente(**ref) for ref in response.data]
        except Exception as e:
            print(f"Error obteniendo referencias: {str(e)}")
            return []