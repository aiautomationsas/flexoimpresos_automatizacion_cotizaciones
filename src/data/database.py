from typing import List, Optional, Dict, Any, Tuple
from src.data.models import (
    Cotizacion, Material, Acabado, Cliente, Escala, ReferenciaCliente,
    TipoProducto, PrecioEscala, TipoGrafado, EstadoCotizacion, MotivoRechazo,
    Adhesivo, TipoFoil, PoliticasEntrega, PoliticasCartera
)
import os
import logging
from datetime import datetime
from dateutil.parser import isoparse
from decimal import Decimal
import streamlit as st
import traceback
import postgrest
import httpx
import time
from supabase import create_client, Client, PostgrestAPIError
import json
import math

class DBManager:
    def _parse_timestamptz(self, value: Any) -> Optional[datetime]:
        """Parsea un timestamptz ISO de Postgres a datetime de forma tolerante.
        Acepta fracciones con 1-6 dígitos y ajusta 'Z' a '+00:00'.
        """
        try:
            if value is None:
                return None
            if isinstance(value, datetime):
                return value
            v = str(value).replace('Z', '+00:00')
            try:
                return datetime.fromisoformat(v)
            except Exception:
                # Normalizar microsegundos a 6 dígitos antes del timezone
                if '.' in v:
                    head, _, tail = v.partition('.')
                    digits = []
                    tz_part = ''
                    for ch in tail:
                        if ch.isdigit() and len(digits) < 6:
                            digits.append(ch)
                        else:
                            tz_part = tail[len(digits):]
                            break
                    micros = ''.join(digits).ljust(6, '0')
                    new_v = f"{head}.{micros}{tz_part}"
                    return datetime.fromisoformat(new_v)
                # Sin fracción, intentar parseo directo
                return datetime.fromisoformat(v)
        except Exception:
            return None
    # --- INICIO DEFINICIÓN CAMPOS ACTUALIZABLES ---
    CAMPOS_COTIZACION_ACTUALIZABLES = {
        'material_adhesivo_id', 'acabado_id', 'tipo_foil_id', 'num_tintas', 'num_paquetes_rollos',
        'es_manga', 'tipo_grafado_id', 'valor_troquel', 'valor_plancha_separado',
        'estado_id', 'id_motivo_rechazo', 'planchas_x_separado', 'existe_troquel',
        'numero_pistas', 'tipo_producto_id', 'ancho', 'avance',
        'altura_grafado', 'es_recotizacion', 'ajustes_modificados_admin',
        'identificador'  # <--- AÑADIR ESTA LÍNEA
    }
    # --- FIN DEFINICIÓN CAMPOS ACTUALIZABLES ---
    
    def __init__(self, supabase_client):
        self.supabase = supabase_client
    
    def _parse_dt(self, value):
        """Parsea de forma segura timestamps ISO (o devuelve el datetime si ya lo es).
        Retorna None si value es falsy o si el parseo falla.
        """
        if not value:
            return None
        if isinstance(value, datetime):
            return value
        try:
            return isoparse(value)
        except Exception:
            return None
        
    def _generar_identificador(self, tipo_producto: str, material_code: str, ancho: float, avance: float,
                           num_pistas: int, num_tintas: int, acabado_code: str, num_paquetes_rollos: int,
                           cliente: str, referencia: str, numero_cotizacion: int) -> str:
        """
        NOTA: Esta función está marcada como legacy/deprecated para la creación de nuevas cotizaciones.
        La generación del identificador para NUEVAS cotizaciones ahora se maneja en la función RPC 'crear_cotizacion'.
        Esta función se mantiene para:
        1. Soporte de actualizaciones de cotizaciones existentes
        2. Referencia de la lógica de generación de identificadores
        3. Propósitos de depuración y pruebas

        Genera un identificador único para la cotización con el siguiente formato:
        TIPO MATERIAL ANCHO_x_AVANCE [TINTAS] [ACABADO] [RX/MX_PAQUETES] CLIENTE REFERENCIA NUMERO_COTIZACION

        Ejemplos:
        - Etiqueta normal: ET PELB 50X50MM 0T LAM RX1000 ENSAYO VLAMOS 150
        - Etiqueta con FOIL: ET PELB 50X50MM 0T+FOIL LAM RX1000 ENSAYO VLAMOS 150
        - Manga: MT PELB 50X50MM 0T MX1000 ENSAYO VLAMOS 150

        Args:
            tipo_producto (str): Nombre del tipo de producto (debe contener 'MANGA' si es manga)
            material_code (str): Código del material (ej: 'PELB')
            ancho (float): Ancho del producto
            avance (float): Avance del producto
            num_pistas (int): Número de pistas
            num_tintas (int): Número de tintas
            acabado_code (str): Código del acabado (ej: 'LAM', 'FOIL+LAM')
            num_paquetes_rollos (int): Número de paquetes o rollos
            cliente (str): Nombre del cliente
            referencia (str): Descripción de la referencia
            numero_cotizacion (int): Número de cotización

        Returns:
            str: Identificador único generado
        """
        # 1. Tipo de producto
        es_manga = "MANGA" in tipo_producto.upper()
        tipo = "MT" if es_manga else "ET"  # Usar MT para mangas, ET para etiquetas
        
        # Formatear dimensiones sin redondear decimales
        try:
            ancho_str = format(Decimal(str(ancho)).normalize(), 'f')
            if '.' in ancho_str:
                ancho_str = ancho_str.rstrip('0').rstrip('.')
        except Exception:
            ancho_str = str(ancho)

        try:
            avance_str = format(Decimal(str(avance)).normalize(), 'f')
            if '.' in avance_str:
                avance_str = avance_str.rstrip('0').rstrip('.')
        except Exception:
            avance_str = str(avance)

        dimensiones = f"{ancho_str}x{avance_str}MM"
        
        # Inicializar las cadenas para tintas y acabado
        tintas_str_final = f"{num_tintas}T"
        acabado_para_id = "" # Código del acabado que irá en el identificador

        print(f"--- DEBUG IDENTIFICADOR ---")
        print(f"Input tipo_producto: {tipo_producto}")
        print(f"Input material_code: {material_code}")
        print(f"Input ancho: {ancho}, avance: {avance}")
        print(f"Input num_tintas: {num_tintas}")
        print(f"Input acabado_code: '{acabado_code}'") # Mostrar comillas para ver espacios
        print(f"Input es_manga: {es_manga}")

        if not es_manga: # Lógica de acabado y modificación de tintas solo para etiquetas
            if acabado_code:
                acabado_code_upper = acabado_code.upper()
                print(f"acabado_code_upper: '{acabado_code_upper}'")
                
                is_foil_with_base = "FOIL" in acabado_code_upper and "+" in acabado_code_upper
                is_just_foil = acabado_code_upper == "FOIL"
                print(f"is_foil_with_base: {is_foil_with_base}")
                print(f"is_just_foil: {is_just_foil}")

                if is_foil_with_base:
                    print("Branch: is_foil_with_base")
                    parts = acabado_code_upper.split('+')
                    print(f"parts: {parts}")
                    # Extraer las partes del código que no son "FOIL"
                    base_code_parts = [p.strip() for p in parts if p.strip() != "FOIL"]
                    print(f"base_code_parts: {base_code_parts}")
                    
                    if base_code_parts:
                        tintas_str_final = f"{num_tintas}T+FOIL"
                        acabado_para_id = "+".join(base_code_parts) # ej. "LAMMAT"
                    else: # Podría ser si el código era "FOIL+" o "FOIL+FOIL" (base vacía)
                        tintas_str_final = f"{num_tintas}T+FOIL"
                        acabado_para_id = "" # No hay código de acabado base para mostrar
                elif is_just_foil:
                    print("Branch: is_just_foil")
                    tintas_str_final = f"{num_tintas}T+FOIL"
                    acabado_para_id = "" # No hay nombre de acabado, solo el efecto foil
                else: # Acabado normal (no FOIL o no sigue los patrones FOIL especiales)
                    print("Branch: acabado_normal")
                    acabado_para_id = acabado_code.split('-')[0].strip()
            else:
                print("No acabado_code para etiqueta.")
        else:
            print("Es manga, no se aplica lógica de FOIL para identificador de acabado/tintas.")
        
        print(f"Intermedio tintas_str_final: {tintas_str_final}")
        print(f"Intermedio acabado_para_id: '{acabado_para_id}'")
        
        # Obtener partes limpias de cliente y referencia (como en el código original)
        cliente_limpio = cliente.split('(')[0].strip().upper() if cliente else ""
        referencia_limpia = referencia.split('(')[0].strip().upper() if referencia else ""
        num = f"{numero_cotizacion}" # Nombre de variable como en el código original
        
        # Construir el identificador pieza por pieza
        identificador_parts = [tipo, material_code, dimensiones]

        # Solo añadir la parte de tintas si num_tintas es mayor que 0
        # o si la lógica de FOIL ya modificó tintas_str_final para incluir "FOIL"
        if num_tintas > 0 or "FOIL" in tintas_str_final:
            identificador_parts.append(tintas_str_final)

        if es_manga:
            paquetes = f"MX{num_paquetes_rollos}"
            identificador_parts.append(paquetes)
        else: # Es etiqueta
            if acabado_para_id: # Solo añadir la parte del acabado si existe
                identificador_parts.append(acabado_para_id)
            
            paquetes = f"RX{num_paquetes_rollos}"
            identificador_parts.append(paquetes)

        # Añadir las partes comunes restantes
        identificador_parts.extend([cliente_limpio, referencia_limpia, num])
        
        # Unir todas las partes con un espacio, filtrando las que puedan ser None o vacías
        identificador = " ".join(filter(None, identificador_parts)) 
        
        # Convertir a mayúsculas (como en el código original)
        identificador_final = identificador.upper()
        print(f"Partes finales del identificador antes de unir: {identificador_parts}")
        print(f"Identificador generado: {identificador_final}") # Mantener el print del código original
        print(f"--- FIN DEBUG IDENTIFICADOR ---")
        
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
        Limpia y filtra los datos ANTES de enviarlos a la base de datos (UPDATE).
        - SOLO incluye campos definidos en CAMPOS_COTIZACION_ACTUALIZABLES.
        - Elimina valores None.
        - Convierte tipos si es necesario.
        """
        campos_booleanos = {'es_manga', 'existe_troquel', 'es_recotizacion', 'planchas_x_separado', 'ajustes_modificados_admin'}
        campos_enteros = {'material_adhesivo_id', 'acabado_id', 'tipo_foil_id', 'num_tintas', 'num_paquetes_rollos',
                         'tipo_grafado_id', 'estado_id', 'id_motivo_rechazo', 'numero_pistas',
                         'tipo_producto_id'}
        campos_numericos = {'valor_troquel', 'valor_plancha_separado', 'ancho', 'avance', 'altura_grafado'}
        
        new_dict = {}
        # --- INICIO CAMBIO LÓGICA: Iterar solo campos permitidos ---
        for k in self.CAMPOS_COTIZACION_ACTUALIZABLES:
            if k in datos_dict and datos_dict[k] is not None:
                v = datos_dict[k]
                # Aplicar conversiones de tipo
                if k in campos_booleanos:
                    if isinstance(v, str):
                        new_dict[k] = v.lower() == 'true'
                    else:
                        new_dict[k] = bool(v)
                elif k in campos_enteros and v != '':
                    try:
                        new_dict[k] = int(v)
                    except (ValueError, TypeError):
                        new_dict[k] = None # O manejar el error como prefieras
                        print(f"Advertencia: No se pudo convertir '{k}' a entero: {v}")
                elif k in campos_numericos and v != '':
                    try:
                        new_dict[k] = float(v)
                    except (ValueError, TypeError):
                        new_dict[k] = None
                        print(f"Advertencia: No se pudo convertir '{k}' a float: {v}")
                else:
                    # Si no requiere conversión específica (y está en la lista permitida)
                    new_dict[k] = v 
        # --- FIN CAMBIO LÓGICA ---
        
        # Asegurarse de que los campos None resultantes de conversiones fallidas no se incluyan
        return {k: v for k, v in new_dict.items() if v is not None}


    def crear_cotizacion(self, datos_cotizacion):
        """Crea una nueva cotización."""
        def _operation():
            # 1. Preparar datos iniciales (sin identificador ni número de cotización predefinido)
            print("\\\\nPreparando datos iniciales para la inserción...")
            # Eliminar campos que asignará la BD o que se usarán después
            datos_cotizacion.pop('id', None) # <-- AÑADIR ESTA LÍNEA
            datos_cotizacion.pop('identificador', None)
            datos_cotizacion.pop('numero_cotizacion', None)
            # --- FIX: Remove datetime fields before sending to JSON/RPC ---
            datos_cotizacion.pop('fecha_creacion', None)
            datos_cotizacion.pop('ultima_modificacion_inputs', None)
            datos_cotizacion.pop('actualizado_en', None) # Remove if it exists too
            # --- Eliminar otros campos no necesarios para la RPC ---
            datos_cotizacion.pop('id_usuario', None) # SQL usa auth.uid()
            datos_cotizacion.pop('id_motivo_rechazo', None) # No aplica en creación
            datos_cotizacion.pop('modificado_por', None) # No aplica en creación
            datos_cotizacion.pop('colores_tinta', None) # Campo de modelo
            datos_cotizacion.pop('politicas_entrega_id', None) # Ya no existe
            datos_cotizacion.pop('material_adhesivo', None) # Objeto relacional
            datos_cotizacion.pop('politicas_entrega', None) # Objeto relacional
            datos_cotizacion.pop('estado_id', None) # SQL lo asigna a 1
            datos_cotizacion.pop('cliente', None) # Eliminar objetos relacionales si existen
            datos_cotizacion.pop('referencia_cliente', None)
            datos_cotizacion.pop('material', None)
            datos_cotizacion.pop('acabado', None)
            datos_cotizacion.pop('tipo_producto', None)

            datos_cotizacion.pop('perfil_comercial_info', None)
            datos_cotizacion.pop('tipo_grafado', None)
            # ---------------------------------------------------------

            # Convertir valores Decimal a float para JSON si es necesario
            for key in ['valor_troquel', 'valor_plancha_separado']:
                if key in datos_cotizacion and datos_cotizacion[key] is not None:
                    try:
                        datos_cotizacion[key] = float(datos_cotizacion[key])
                    except (TypeError, ValueError):
                        print(f"Error convirtiendo {key} a float")
                        datos_cotizacion[key] = 0.0
            

            
            
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
                # Obtener IDs finales desde la respuesta de la RPC
                material_adhesivo_id_final = cotizacion_creada_data.get('material_adhesivo_id')
                acabado_id_final = cotizacion_creada_data.get('acabado_id')
                referencia_id_final = cotizacion_creada_data.get('referencia_cliente_id')
                tipo_producto_id_final = cotizacion_creada_data.get('tipo_producto_id') # Asumiendo que lo devuelve la RPC
                es_manga_final = cotizacion_creada_data.get('es_manga', False) # Asumiendo que lo devuelve la RPC

                # Determinar tipo de producto
                # TODO: Obtener nombre de tipo_producto basado en tipo_producto_id_final si es necesario
                tipo_producto_nombre = "MANGA" if es_manga_final else "ETIQUETA" 

                # --- Obtener el código del material directamente desde material_adhesivo --- 
                # material_id_final = self.get_material_id_from_material_adhesivo(material_adhesivo_id_final) if material_adhesivo_id_final else None
                # material_code = self.get_material_code(material_id_final) if material_id_final else ""
                material_code = self.get_material_adhesivo_code(material_adhesivo_id_final) if material_adhesivo_id_final else ""
                # --------------------------------------------------------------------------
                
                # Obtener código de acabado (solo si no es manga)
                acabado_code = self.get_acabado_code(acabado_id_final) if not es_manga_final and acabado_id_final else ""
                
                # Obtener referencia y cliente usando el ID final
                referencia = self.get_referencia_cliente(referencia_id_final) if referencia_id_final else None
                if not referencia:
                    raise ValueError(f"No se encontró la referencia {referencia_id_final} después de crear cotización")
                
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
                # Obtener otros datos necesarios del diccionario original o de la respuesta RPC
                ancho = datos_cotizacion.get('ancho', cotizacion_creada_data.get('ancho', 0))
                avance = datos_cotizacion.get('avance', cotizacion_creada_data.get('avance', 0))
                num_pistas = datos_cotizacion.get('numero_pistas', cotizacion_creada_data.get('numero_pistas', 1))
                num_tintas = datos_cotizacion.get('num_tintas', cotizacion_creada_data.get('num_tintas', 0))
                num_paquetes_rollos = datos_cotizacion.get('num_paquetes_rollos', cotizacion_creada_data.get('num_paquetes_rollos', 0))

                identificador_final = self._generar_identificador(
                    tipo_producto=tipo_producto_nombre,
                    material_code=material_code, # Usar código correcto
                    ancho=ancho,
                    avance=avance,
                    num_pistas=num_pistas,
                    num_tintas=num_tintas,
                    acabado_code=acabado_code, # Usar código correcto
                    num_paquetes_rollos=num_paquetes_rollos,
                    cliente=cliente_nombre, # Usar nombre correcto
                    referencia=referencia_descripcion, # Usar descripción correcta
                    numero_cotizacion=numero_cotizacion_final # Usar el número final de la BD
                )
                print(f"Identificador final generado: {identificador_final}")
            except Exception as e:
                print(f"Error generando identificador final: {e}")
                # Decidir qué hacer: continuar sin identificador o fallar?
                # Por ahora, continuamos pero registramos el error. El campo será "" o el valor por defecto.
                # Loguear la advertencia en lugar de usar st.warning directamente en backend
                logging.warning(f"No se pudo generar el identificador para la cotización {cotizacion_id}. Error: {e}", exc_info=True)
                # Considerar lanzar una excepción específica si la generación del ID es crítica
                # raise IdentificadorGenerationError(f"Fallo al generar identificador: {e}") from e


            # 5. Actualizar la cotización con el identificador generado
            if identificador_final:
                print(f"\\nActualizando cotización {cotizacion_id} con el identificador final...")
                try:
                    print(f"DEBUG - Intentando actualizar identificador. Cotización ID: {cotizacion_id}, Identificador: {identificador_final}")
                    update_response = self.supabase.table('cotizaciones').update({"identificador": identificador_final}).eq('id', cotizacion_id).execute()
                    print(f"DEBUG - Respuesta completa: {update_response}")
                    
                    # --- Verificar si hubo error explícito ---
                    update_successful = True # Asumir éxito por defecto
                    update_error = None
                    if hasattr(update_response, 'error') and update_response.error:
                         update_successful = False
                         update_error = update_response.error
                         print(f"Error DETECTADO en respuesta de Supabase: {update_error}")
                    # Comprobación adicional por si la estructura cambia o el error está en data
                    elif not update_response.data and (not hasattr(update_response, 'status_code') or update_response.status_code < 200 or update_response.status_code >= 300):
                         update_successful = False
                         print(f"Error: Respuesta sin datos y con código de estado de error: {getattr(update_response, 'status_code', 'N/A')}")
                    # Ausencia de error explícito se considera éxito.

                    if not update_successful:
                        print(f"Error: No se pudo actualizar la cotización {cotizacion_id} con el identificador.")
                        # Imprimir más detalles de diagnóstico
                        if update_error: # Usar el error capturado
                            print(f"Error detallado: {update_error}")
                        # Usar logging en lugar de st.warning
                        logging.warning(f"Cotización {cotizacion_id} creada, pero falló la actualización del identificador. Error: {update_error}") 
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
            print(f"\n=== ACTUALIZANDO COTIZACIÓN {cotizacion_id} VÍA RPC ===") # Mensaje actualizado
            print("Datos a actualizar (antes de limpiar):", datos_cotizacion)
            
            # --- INICIO: Log especial para ajustes_modificados_admin ---
            flag_ajustes_admin = datos_cotizacion.get('ajustes_modificados_admin')
            print(f"🚩 Flag ajustes_modificados_admin en datos recibidos: {flag_ajustes_admin} (tipo: {type(flag_ajustes_admin).__name__})")
            # --- FIN: Log especial ---
            
            # --- INICIO: Extraer identificador si existe ---
            identificador = datos_cotizacion.get('identificador')
            print(f"🏷️ Identificador para posible actualización posterior: {identificador}")
            # --- FIN: Extraer identificador ---
            
            # Validar estado y motivo de rechazo (si aplica)
            estado_id = datos_cotizacion.get('estado_id')
            id_motivo_rechazo = datos_cotizacion.get('id_motivo_rechazo')
            if estado_id == 3 and id_motivo_rechazo is None:
                return False, "❌ Se requiere un motivo de rechazo cuando el estado es 'Rechazado'"
            
            # Limpiar datos ANTES de enviar a RPC
            datos_limpios = self._limpiar_datos(datos_cotizacion)
            print("\nDatos limpios a enviar a RPC:")
            for k, v in datos_limpios.items():
                print(f"  {k}: {v}")
                
            # --- INICIO: Log especial post-limpieza ---
            if 'ajustes_modificados_admin' in datos_limpios:
                print(f"🚩 Flag ajustes_modificados_admin (después de limpieza): {datos_limpios['ajustes_modificados_admin']}")
            else:
                print("❌ ERROR: Flag ajustes_modificados_admin ELIMINADO durante limpieza!")
            # --- FIN: Log especial ---
                
            # --- AÑADIR CAMPOS DE AUDITORÍA ---
            # La RPC debería manejar esto internamente basado en auth.uid() y now()
            # pero los pasamos por ahora para consistencia, la RPC puede ignorarlos si prefiere.
            user_id = st.session_state.get('user_id') 
            if user_id:
                datos_limpios['modificado_por'] = user_id
            else:
                 print("ADVERTENCIA: No se encontró user_id en session_state para auditoría (RPC). La RPC debería usar auth.uid().")
            # datos_limpios['actualizado_en'] = datetime.now().isoformat() # La RPC debería usar now()
            # ---------------------------------
            
            # --- LLAMADA A RPC --- 
            print(f"\nLlamando a RPC 'actualizar_cotizacion_rpc' para ID {cotizacion_id}...")
            
            # Llamar a la RPC solo con los parámetros que acepta
            response = self.supabase.rpc(
                'actualizar_cotizacion_rpc',
                {'p_cotizacion_id': cotizacion_id, 'p_datos': datos_limpios}
            ).execute()
            # ----------------------
            
            # Verificar la respuesta de la RPC
            # Asumimos que la RPC devuelve la fila actualizada (o al menos el ID) si tiene éxito
            if response.data and isinstance(response.data, list) and len(response.data) > 0:
                print(f"RPC actualizar_cotizacion_rpc exitosa. Fila actualizada: {response.data[0]}")
                
                # FASE 2: Verificar si necesitamos actualizar manualmente algunos campos
                # Para esto realizamos un segundo paso de actualización directa solo si es necesario
                updates_pendientes = {}
                
                # 1. Verificar si el identificador se actualizó correctamente
                respuesta_identificador = None
                if isinstance(response.data[0], dict):
                    respuesta_identificador = response.data[0].get('identificador')
                
                # Si tenemos identificador a actualizar y no coincide con la respuesta, añadirlo a la lista
                if identificador and (respuesta_identificador is None or respuesta_identificador != identificador):
                    print(f"⚠️ Identificador no actualizado por RPC. Programando actualización manual: '{respuesta_identificador}' → '{identificador}'")
                    updates_pendientes['identificador'] = identificador
                
                # 2. Verificar si el flag ajustes_modificados_admin se actualizó correctamente
                if 'ajustes_modificados_admin' in datos_limpios:
                    flag_enviado = datos_limpios['ajustes_modificados_admin']
                    respuesta_flag = None
                    
                    if isinstance(response.data[0], dict):
                        respuesta_flag = response.data[0].get('ajustes_modificados_admin')
                    
                    # Si el flag enviado es True pero no se aplicó correctamente, añadirlo a la lista
                    if flag_enviado is True and respuesta_flag is not True:
                        print(f"⚠️ Flag ajustes_modificados_admin no actualizado por RPC. Programando actualización manual: {respuesta_flag} → True")
                        updates_pendientes['ajustes_modificados_admin'] = True
                
                # 3. Si tenemos actualizaciones pendientes, hacerlas en una sola operación
                if updates_pendientes:
                    print(f"Realizando actualización manual para campos: {list(updates_pendientes.keys())}")
                    try:
                        # Actualizar directamente en la tabla cotizaciones
                        update_result = self.supabase.table('cotizaciones') \
                            .update(updates_pendientes) \
                .eq('id', cotizacion_id) \
                .execute()
            
                        if hasattr(update_result, 'error') and update_result.error:
                            print(f"❌ Error en actualización manual: {update_result.error}")
                        else:
                            print(f"✅ Actualización manual completada con éxito.")
                    except Exception as e_update:
                        print(f"❌ Error en la actualización manual: {e_update}")
                
                return True, "✅ Cotización actualizada exitosamente (vía RPC)"
            # Algunas RPC pueden devolver un solo objeto
            elif response.data and isinstance(response.data, dict) and response.data:
                print(f"RPC actualizar_cotizacion_rpc exitosa. Respuesta: {response.data}")
                 
                # FASE 2: Verificar si necesitamos actualizar manualmente algunos campos
                updates_pendientes = {}
                
                # 1. Verificar si el identificador se actualizó correctamente
                respuesta_identificador = response.data.get('identificador')
                
                # Si tenemos identificador a actualizar y no coincide con la respuesta, añadirlo a la lista
                if identificador and (respuesta_identificador is None or respuesta_identificador != identificador):
                    print(f"⚠️ Identificador no actualizado por RPC. Programando actualización manual: '{respuesta_identificador}' → '{identificador}'")
                    updates_pendientes['identificador'] = identificador
                
                # 2. Verificar si el flag ajustes_modificados_admin se actualizó correctamente
                if 'ajustes_modificados_admin' in datos_limpios:
                    flag_enviado = datos_limpios['ajustes_modificados_admin']
                    respuesta_flag = response.data.get('ajustes_modificados_admin')
                    
                    # Si el flag enviado es True pero no se aplicó correctamente, añadirlo a la lista
                    if flag_enviado is True and respuesta_flag is not True:
                        print(f"⚠️ Flag ajustes_modificados_admin no actualizado por RPC. Programando actualización manual: {respuesta_flag} → True")
                        updates_pendientes['ajustes_modificados_admin'] = True
                
                # 3. Si tenemos actualizaciones pendientes, hacerlas en una sola operación
                if updates_pendientes:
                    print(f"Realizando actualización manual para campos: {list(updates_pendientes.keys())}")
                    try:
                        # Actualizar directamente en la tabla cotizaciones
                        update_result = self.supabase.table('cotizaciones') \
                            .update(updates_pendientes) \
                            .eq('id', cotizacion_id) \
                            .execute()
                        
                        if hasattr(update_result, 'error') and update_result.error:
                            print(f"❌ Error en actualización manual: {update_result.error}")
                        else:
                            print(f"✅ Actualización manual completada con éxito.")
                    except Exception as e_update:
                        print(f"❌ Error en la actualización manual: {e_update}")
                
                return True, "✅ Cotización actualizada exitosamente (vía RPC)"
            else:
                # Si no hay datos, verificar si hay un error explícito
                error_info = getattr(response, 'error', None)
                error_msg_rpc = f"Error RPC: {error_info}" if error_info else "La RPC de actualización no devolvió datos confirmatorios."
                print(f"Error en RPC update: {error_msg_rpc}") 
                # Intentar extraer un mensaje más útil del error si es posible
                detailed_error = ""                
                if error_info and hasattr(error_info, 'message'):
                    detailed_error = error_info.message
                elif isinstance(response.data, dict) and 'message' in response.data:
                    detailed_error = response.data['message'] # A veces el error viene en data

                final_error_msg = f"❌ {error_msg_rpc}" + (f" ({detailed_error})" if detailed_error else "")
                return False, final_error_msg
            
        except Exception as e: # Capturar errores generales
            error_msg = str(e)
            print(f"Error al actualizar cotización vía RPC (bloque except general): {error_msg}")
            traceback.print_exc()
            return False, f"❌ Error técnico al actualizar vía RPC: {error_msg}"

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
                
                # --- CORRECCIÓN: Verificar si hubo un error en la respuesta, no solo si .data está vacío --- 
                if hasattr(insert_result, 'error') and insert_result.error:
                    print(f"Error durante la inserción de escalas: {insert_result.error}")
                    return False # Hubo un error
                # Ya no necesitamos la condición 'if not insert_result.data:' aquí
                # porque una inserción exitosa puede no devolver datos.
                # Consideramos éxito si no hubo error.
                # --- FIN CORRECCIÓN ---
                    
                # Este log ahora es más informativo
                print(f"Inserción de escalas completada (sin errores reportados por Supabase).") 
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
                    .order('nombre', desc=False)\
                    .execute()

                return [Cliente(
                    id=cliente['id'],
                    nombre=cliente['nombre'],
                    codigo=cliente.get('codigo'),
                    persona_contacto=cliente.get('persona_contacto'),
                    correo_electronico=cliente.get('correo_electronico'),
                    telefono=cliente.get('telefono'),
                    creado_en=self._parse_timestamptz(cliente.get('creado_en')),
                    actualizado_en=self._parse_timestamptz(cliente.get('actualizado_en'))
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
            # Corrección: Seleccionar solo campos de 'materiales', eliminar relación inexistente con 'adhesivos'
            response = self.supabase.from_('materiales').select(
                'id, nombre' # Seleccionar solo las columnas que existen: id, nombre
                # Quitar: ', valor, updated_at, code, id_adhesivos, adhesivos(tipo)'
            ).eq('id', material_id).single().execute() # Usar .single() para obtener un solo objeto o error
            
            # El resultado ahora debería ser un solo diccionario o None
            if response.data:
                # Crear el objeto Material directamente
                return Material(**response.data)
            else:
                print(f"No se encontró material con ID {material_id} (o hubo un error)")
                return None
            
            # --- Lógica anterior eliminada --- 
            # if not response.data or len(response.data) == 0:
            #     print(f"No se encontró material con ID {material_id}")
            #     return None
            # 
            # # Procesar el resultado para aplanar la estructura
            # item = response.data[0]
            # material_data = {
            #     'id': item['id'],
            #     'nombre': item['nombre'],
            #     'valor': item['valor'],
            #     'updated_at': item['updated_at'],
            #     'code': item['code'],
            #     'id_adhesivos': item['id_adhesivos'],
            #     'adhesivo_tipo': item['adhesivos']['tipo'] if item['adhesivos'] else None
            # }
            # 
            # return Material(**material_data)
            # --- Fin lógica eliminada ---
            
        except PostgrestAPIError as api_error:
            # Capturar específicamente APIError para ver detalles
            print(f"Error de API Supabase al obtener material: {api_error}")
            traceback.print_exc()
            return None
        except Exception as e:
            print(f"Error general al obtener material: {e}")
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

    def get_tipos_foil(self) -> List[TipoFoil]:
        """Obtiene la lista de tipos de foil disponibles."""
        def _operation():
            response = self.supabase.table('tipos_foil').select('*').execute()
            if response.data:
                return [TipoFoil.from_dict(item) for item in response.data]
            return []
        return self._retry_operation("get_tipos_foil", _operation)

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
        """Obtiene clientes sujetos a RLS (admin ve todos; comercial solo los propios)."""
        def _operation():
            print("\n=== DEBUG: Consultando clientes con RLS activo ===")
            response = (
                self.supabase
                .from_('clientes')
                .select('*')
                .order('nombre', desc=False)
                .execute()
            )

            if response is None:
                print("ERROR: La respuesta de Supabase fue None en get_clientes.")
                raise ConnectionError("Supabase devolvió None en get_clientes")

            if not response.data:
                print("No se encontraron clientes (RLS)")
                return []

            clientes: List[Cliente] = []
            for item in response.data:
                try:
                    clientes.append(Cliente(**item))
                except TypeError as te:
                    print(f"Error creando objeto Cliente desde datos: {te}")
                    print(f"Datos del item problemático: {item}")
                    continue

            print(f"Se encontraron {len(clientes)} clientes (RLS)")
            return clientes

        try:
            return self._retry_operation("obtener clientes (RLS)", _operation)
        except ConnectionError as ce:
            print(f"Error de conexión persistente en get_clientes: {ce}")
            raise
        except Exception as e:
            print(f"Error al obtener clientes: {str(e)}")
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

    def actualizar_cliente(self, cliente_id: int, cambios: Dict[str, Any]) -> bool:
        """Actualiza campos permitidos de un cliente.
        RLS: Comercial solo si es dueña (vía referencias_cliente); admin puede todos.
        """
        campos_permitidos = {
            'nombre', 'persona_contacto', 'correo_electronico', 'telefono', 'codigo'
        }
        data = {k: v for k, v in cambios.items() if k in campos_permitidos}
        # Validar y normalizar NIT/CC (codigo) si viene en cambios
        if 'codigo' in data:
            try:
                codigo_limpio = str(data['codigo']).strip().replace('-', '').replace('.', '')
                if not codigo_limpio.isdigit():
                    print("actualizar_cliente: 'codigo' debe ser numérico")
                    return False
                data['codigo'] = int(codigo_limpio)
            except Exception as e_norm:
                print(f"Error normalizando 'codigo' en actualizar_cliente: {e_norm}")
                return False
        if not data:
            print("No hay campos válidos para actualizar en cliente")
            return False
        try:
            # Nota: el cliente Python no soporta encadenar .select después de update
            resp = (
                self.supabase
                .from_('clientes')
                .update(data)
                .eq('id', cliente_id)
                .execute()
            )
            # Si RLS bloquea, se lanzará APIError y caerá en except
            return resp is not None
        except Exception as e:
            print(f"Error actualizando cliente {cliente_id}: {e}")
            traceback.print_exc()
            return False

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
        """
        Crea un nuevo cliente en la base de datos.
        """
        print("\n=== INICIO CREAR CLIENTE ===")
        print(f"Cliente recibido: {cliente.__dict__}")
        
        try:
            # Validar campos requeridos
            if not cliente.nombre or not cliente.nombre.strip():
                raise Exception("El nombre del cliente es requerido")
                
            if not cliente.codigo:
                raise Exception("El código (NIT/CC) del cliente es requerido")
                
            # Validar que el código sea numérico y limpiarlo
            codigo_limpio = str(cliente.codigo).replace('-', '').replace('.', '')
            if not codigo_limpio.isdigit():
                raise Exception("El código (NIT/CC) debe contener solo números")
            
            # Convertir a bigint
            try:
                codigo_numerico = int(codigo_limpio)
            except ValueError:
                raise Exception(f"No se pudo convertir el código '{codigo_limpio}' a número")
            
            # Preparar datos para RPC atómica (cliente + referencia dueña)
            rpc_data = {
                'p_nombre': cliente.nombre.strip(),
                'p_codigo': codigo_numerico,  # Enviar como bigint
                'p_persona_contacto': cliente.persona_contacto.strip() if cliente.persona_contacto else None,
                'p_correo_electronico': cliente.correo_electronico.strip() if cliente.correo_electronico else None,
                'p_telefono': cliente.telefono.strip() if cliente.telefono else None,
                'p_descripcion': 'Principal'
            }
            
            print("\nDatos que se enviarán:")
            for k, v in rpc_data.items():
                print(f"  {k}: {v} (tipo: {type(v)})")
            
            # Intentar crear cliente + referencia con RPC segura
            try:
                response = self.supabase.rpc(
                    'crear_cliente_y_referencia',
                    rpc_data
                ).execute()
            except Exception as e_rpc:
                print(f"Error llamando a crear_cliente_y_referencia: {e_rpc}")
                raise

            if not response or not response.data:
                raise Exception("No se pudo crear el cliente (sin datos de RPC)")

            # La RPC retorna (cliente_id, referencia_id)
            result = response.data[0]
            cliente_id = result.get('cliente_id') if isinstance(result, dict) else None
            if not cliente_id:
                raise Exception("La RPC no retornó cliente_id")

            # Recuperar el cliente creado sujeto a RLS
            cliente_creado = self.get_cliente(int(cliente_id))
            if not cliente_creado:
                # Fallback: construir objeto mínimo si no se puede leer aún
                cliente_creado = Cliente(
                    id=int(cliente_id),
                    nombre=cliente.nombre.strip(),
                    codigo=codigo_numerico,
                    persona_contacto=rpc_data['p_persona_contacto'],
                    correo_electronico=rpc_data['p_correo_electronico'],
                    telefono=rpc_data['p_telefono']
                )
            return cliente_creado
                
        except Exception as e:
            print("\n!!! ERROR EN CREAR_CLIENTE !!!")
            print(f"Tipo de error: {type(e)}")
            print(f"Mensaje de error: {str(e)}")
            
            if 'rpc_data' in locals():
                print("\nDatos que se intentaron insertar:")
                for k, v in rpc_data.items():
                    print(f"  {k}: {v} (tipo: {type(v)})")
            
            print("\nStack trace completo:")
            import traceback
            traceback.print_exc()
            
            raise Exception(f"Error al crear cliente: {str(e)}")

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

            # Verificar si ya existe una referencia con la misma descripción para este cliente y ese usuario objetivo
            existing = self.supabase.rpc(
                'check_referencia_exists',
                {
                    'p_cliente_id': referencia.cliente_id,
                    'p_descripcion': data['descripcion'],
                    'p_id_usuario': user_id_to_use
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
            
            # --- INICIO CAMBIO: Obtener material correctamente ---
            # material = cotizacion.material # <-- ESTO FALLA
            material_adhesivo_info = cotizacion.material_adhesivo # Es un dict o None
            material_obj = None
            material_id_from_join = None
            if material_adhesivo_info:
                 material_id_from_join = material_adhesivo_info.get('material_id')
                 if material_id_from_join:
                      # Usar el método existente para obtener el objeto Material completo
                      material_obj = self.get_material(material_id_from_join) 
                      if not material_obj:
                           print(f"Advertencia: No se encontró el objeto Material para ID {material_id_from_join} obtenido de material_adhesivo_info")
                 else:
                      print("Advertencia: material_adhesivo_info no contiene 'material_id'")
            else:
                 print("Advertencia: cotizacion.material_adhesivo es None")
            # --- FIN CAMBIO ---

            acabado = cotizacion.acabado
            tipo_producto = cotizacion.tipo_producto

            
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
                # --- INICIO CAMBIO: Usar material_obj ---
                'material': material_obj.__dict__ if material_obj else {}, 
                # --- FIN CAMBIO ---
                'acabado': acabado.__dict__ if acabado else {},
                'num_tintas': cotizacion.num_tintas,
                'num_rollos': cotizacion.num_paquetes_rollos,
                'es_manga': cotizacion.es_manga,
                'tipo_grafado': cotizacion.tipo_grafado_id, # Mantener como ID
                'altura_grafado': cotizacion.altura_grafado, # Añadir la altura del grafado
                'valor_plancha_separado': cotizacion.valor_plancha_separado or 0,
                'planchas_x_separado': cotizacion.planchas_x_separado, # Añadir este campo
                'cliente': cliente_dict,
                'comercial': perfil_comercial, # Ya es un dict
                'identificador': cotizacion.identificador,
                'tipo_producto': tipo_producto.__dict__ if tipo_producto else {},
                # Agregar los valores para el PDF de materiales
                'valor_material': valor_material,
                'valor_acabado': valor_acabado,
                'valor_troquel': valor_troquel,
                # --- NUEVO: Añadir nombre de Tipo Foil ---
                'tipo_foil_nombre': cotizacion.tipo_foil.nombre if cotizacion.tipo_foil else None,
                # -----------------------------------------
                # Información adicional de impresión
                'ancho': calculos.get('ancho', 0) if calculos else 0,
                'avance': calculos.get('avance', 0) if calculos else 0,
                'numero_pistas': calculos.get('numero_pistas', 0) if calculos else 0,
                'desperdicio_total': calculos.get('desperdicio_total', 0) if calculos else 0,
    

            }
            
            # --- INICIO: Añadir Adhesivo Tipo ---
            adhesivo_tipo_final = "No aplica" # Valor por defecto
            # Intentar obtener el tipo del objeto Adhesivo si existe en la cotización
            adhesivo_id_real = None
            if cotizacion.material_adhesivo_id:
                 # Obtener el adhesivo_id real desde la tabla de unión
                 adhesivo_id_real = self.get_adhesivo_id_from_material_adhesivo(cotizacion.material_adhesivo_id)

            if adhesivo_id_real:
                # Si tenemos un ID de adhesivo, buscar su tipo en la tabla 'adhesivos'
                try:
                    temp_adhesivo_response = self.supabase.table('adhesivos').select('tipo').eq('id', adhesivo_id_real).maybe_single().execute()
                    if temp_adhesivo_response.data and temp_adhesivo_response.data.get('tipo'):
                        adhesivo_tipo_final = temp_adhesivo_response.data['tipo']
                    else:
                         print(f"Advertencia: No se encontró tipo para adhesivo_id {adhesivo_id_real}")
                except Exception as e_adh:
                    print(f"Error buscando tipo de adhesivo para ID {adhesivo_id_real}: {e_adh}")

            datos['adhesivo_tipo'] = adhesivo_tipo_final
            print(f"  Adhesivo Tipo añadido al diccionario final: {adhesivo_tipo_final}")
            # --- FIN: Añadir Adhesivo Tipo ---

            # --- INICIO: Añadir Política de Entrega ---
            politica_entrega_descripcion = None
            # Verificar si es etiqueta o manga
            es_etiqueta = not cotizacion.es_manga
            
            # Determinar el ID de política según el tipo de producto
            politica_id = 1 if es_etiqueta else 2  # ID 1 para etiquetas, ID 2 para mangas
            
            try:
                politica_response = self.supabase.table('politicas_entrega').select('descripcion').eq('id', politica_id).maybe_single().execute()
                if politica_response.data and politica_response.data.get('descripcion'):
                    politica_entrega_descripcion = politica_response.data['descripcion']
                    print(f"  Política de entrega encontrada para {'etiqueta' if es_etiqueta else 'manga'} (ID {politica_id}): {politica_entrega_descripcion}")
                else:
                    print(f"  Advertencia: No se encontró descripción para política de entrega con ID {politica_id}")
            except Exception as e_pol:
                print(f"  Error al buscar política de entrega con ID {politica_id}: {e_pol}")
            
            # Agregar al diccionario final
            datos['politica_entrega'] = politica_entrega_descripcion or "Estándar"  # Valor por defecto si no se encuentra
            # --- FIN: Añadir Política de Entrega ---

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

            print(f"  Política de Entrega: {datos.get('politica_entrega')}") # Imprimir política de entrega

            # Procesar las escalas desde el objeto cotizacion.escalas
            datos['resultados'] = [] # Inicializar siempre la lista
            if cotizacion.escalas:
                print(f"\nProcesando {len(cotizacion.escalas)} escalas...")
                for escala in cotizacion.escalas:
                    # Mantener la escala como está
                    escala_valor_original = escala.escala
                    
                    # Redondear el valor_unidad al entero superior
                    valor_unidad_original = escala.valor_unidad
                    valor_unidad_redondeado = None
                    
                    try:
                        # Convertir y redondear hacia arriba el valor_unidad
                        if isinstance(valor_unidad_original, (float, int)):
                            valor_unidad_float = float(valor_unidad_original)
                        elif isinstance(valor_unidad_original, str):
                            valor_unidad_float = float(valor_unidad_original.replace('$', '').replace(',', '').strip())
                        else:
                            valor_unidad_float = 0.0
                            
                        # Aplicar redondeo hacia arriba
                        valor_unidad_redondeado = math.ceil(valor_unidad_float)
                        print(f"  Valor unidad redondeado: {valor_unidad_original} → {valor_unidad_redondeado}")
                    except Exception as e_round:
                        print(f"  Error al redondear valor_unidad '{valor_unidad_original}': {e_round}")
                        valor_unidad_redondeado = valor_unidad_original
                        
                    resultado = {
                        'escala': escala_valor_original,
                        'valor_unidad': valor_unidad_redondeado, # Usar el valor redondeado
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
                'tipo_foil_id': cotizacion.tipo_foil_id,  # Agregado campo tipo_foil_id
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
                                unidad_z_dientes: float, altura_grafado: Optional[float]=None, 
                                valor_plancha_separado: Optional[float] = None,
                                parametros_especiales: Optional[Dict[str, Any]] = None) -> bool:
        """Guarda o actualiza los cálculos de escala para una cotización"""
        try:
            print("\nGuardando cálculos de escala actualizados...")
            
            # Preparar parámetros para la RPC
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
                'p_tipo_grafado_id': tipo_grafado_id,
                'p_valor_acabado': valor_acabado,
                'p_unidad_z_dientes': unidad_z_dientes
            }
            
            print(f"\nLlamando a RPC 'upsert_calculos_escala' para cotizacion_id: {cotizacion_id}")
            print(f"Parámetros RPC: {rpc_params}")
            
            # Llamar a la RPC
            response = self.supabase.rpc('upsert_calculos_escala', rpc_params).execute()
            
            if response.data:
                print("Cálculos de escala guardados exitosamente")
                # Intentar guardar parametros_especiales si fueron provistos
                if parametros_especiales:
                    try:
                        print("Guardando parametros_especiales adjuntos...")
                        _ = (
                            self.supabase
                            .from_('calculos_escala_cotizacion')
                            .update({'parametros_especiales': parametros_especiales})
                            .eq('cotizacion_id', cotizacion_id)
                            .execute()
                        )
                    except Exception as e_save_params:
                        # No bloquear el flujo si la columna no existe o no hay permisos
                        print(f"ADVERTENCIA: No se pudieron guardar parametros_especiales: {e_save_params}")
                return True
            else:
                print("No se recibió respuesta al guardar cálculos de escala")
                return False
                
        except Exception as e:
            print(f"Error de API (Postgrest) al guardar cálculos escala: {e}")
            traceback.print_exc()
            return False

    def guardar_parametros_especiales(self, cotizacion_id: int, parametros_especiales: Optional[Dict[str, Any]]) -> bool:
        """Guarda un JSON de parametros_especiales en calculos_escala_cotizacion si la columna existe.
        No falla en caso de error de esquema/permiso; devuelve False pero deja fluir.
        """
        try:
            if not parametros_especiales:
                return True
            _ = (
                self.supabase
                .from_('calculos_escala_cotizacion')
                .update({'parametros_especiales': parametros_especiales})
                .eq('cotizacion_id', cotizacion_id)
                .execute()
            )
            return True
        except Exception as e:
            print(f"ADVERTENCIA: No se pudieron guardar parametros_especiales (¿columna ausente?): {e}")
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

    def get_calculos_persistidos(self, cotizacion_id: int) -> Optional[Dict]:
        """
        Obtiene los cálculos persistidos de una cotización formateados para generar el informe técnico.
        
        Args:
            cotizacion_id (int): ID de la cotización
            
        Returns:
            Dict: Diccionario con los datos de cálculos necesarios para el informe técnico
        """
        try:
            calculos = self.get_calculos_escala_cotizacion(cotizacion_id)
            if not calculos:
                return None
            return calculos
        except Exception as e:
            print(f"Error en get_calculos_persistidos: {e}")
            traceback.print_exc()
            return None

    # ============================
    #  Políticas de Entrega (CRUD)
    # ============================
    def get_politicas_entrega(self) -> List[PoliticasEntrega]:
        try:
            response = self.supabase.table('politicas_entrega').select('*').order('id').execute()
            return [PoliticasEntrega(
                id=item.get('id'),
                descripcion=item.get('descripcion', ''),
                created_at=self._parse_dt(item.get('created_at')),
                updated_at=self._parse_dt(item.get('updated_at')),
            ) for item in (response.data or [])]
        except Exception as e:
            print(f"Error al obtener políticas de entrega: {e}")
            return []

    def get_politica_entrega(self, politica_id: int) -> Optional[PoliticasEntrega]:
        try:
            response = self.supabase.table('politicas_entrega').select('*').eq('id', politica_id).maybe_single().execute()
            data = response.data if isinstance(response.data, dict) else None
            if not data:
                return None
            return PoliticasEntrega(
                id=data.get('id'),
                descripcion=data.get('descripcion', ''),
                created_at=self._parse_dt(data.get('created_at')),
                updated_at=self._parse_dt(data.get('updated_at')),
            )
        except Exception as e:
            print(f"Error al obtener política de entrega: {e}")
            return None

    def create_politica_entrega(self, politica: PoliticasEntrega) -> bool:
        try:
            payload = {
                'descripcion': politica.descripcion,
            }
            resp = self.supabase.table('politicas_entrega').insert(payload).execute()
            return bool(resp.data)
        except Exception as e:
            print(f"Error al crear política de entrega: {e}")
            return False

    def update_politica_entrega(self, politica: PoliticasEntrega) -> bool:
        try:
            payload = {
                'descripcion': politica.descripcion,
                'updated_at': datetime.now().isoformat()
            }
            resp = self.supabase.table('politicas_entrega').update(payload).eq('id', politica.id).execute()
            return bool(resp.data)
        except Exception as e:
            print(f"Error al actualizar política de entrega: {e}")
            return False

    def delete_politica_entrega(self, politica_id: int) -> bool:
        try:
            resp = self.supabase.table('politicas_entrega').delete().eq('id', politica_id).execute()
            return bool(resp.data)
        except Exception as e:
            print(f"Error al eliminar política de entrega: {e}")
            return False

    def get_cotizaciones_by_politica(self, politica_id: int) -> List[Dict[str, Any]]:
        try:
            resp = self.supabase.table('cotizaciones').select('id').eq('politicas_entrega_id', politica_id).execute()
            return resp.data or []
        except Exception:
            return []

    # ==========================
    #  Políticas de Cartera CRUD
    # ==========================
    def get_politicas_cartera(self) -> List[PoliticasCartera]:
        try:
            response = self.supabase.table('politicas_cartera').select('*').order('id').execute()
            return [PoliticasCartera(
                id=item.get('id'),
                descripcion=item.get('descripcion', ''),
                created_at=self._parse_dt(item.get('created_at')),
                updated_at=self._parse_dt(item.get('updated_at')),
            ) for item in (response.data or [])]
        except Exception as e:
            print(f"Error al obtener políticas de cartera: {e}")
            return []

    def get_politica_cartera(self, politica_id: int) -> Optional[PoliticasCartera]:
        try:
            response = self.supabase.table('politicas_cartera').select('*').eq('id', politica_id).maybe_single().execute()
            data = response.data if isinstance(response.data, dict) else None
            if not data:
                return None
            return PoliticasCartera(
                id=data.get('id'),
                descripcion=data.get('descripcion', ''),
                created_at=self._parse_dt(data.get('created_at')),
                updated_at=self._parse_dt(data.get('updated_at')),
            )
        except Exception as e:
            print(f"Error al obtener política de cartera: {e}")
            return None

    def create_politicas_cartera_table_if_not_exists(self) -> bool:
        try:
            # Solo helper: crear tabla simple si no existe
            self.supabase.rpc('exec_sql', {
                'p_sql': """
                create table if not exists public.politicas_cartera (
                  id serial primary key,
                  descripcion text not null,
                  created_at timestamptz default now(),
                  updated_at timestamptz default now()
                );
                """
            }).execute()
            return True
        except Exception as e:
            print(f"Error creando tabla politicas_cartera: {e}")
            return False

    def create_politica_cartera(self, politica: PoliticasCartera) -> bool:
        try:
            payload = {
                'descripcion': politica.descripcion,
            }
            resp = self.supabase.table('politicas_cartera').insert(payload).execute()
            return bool(resp.data)
        except Exception as e:
            print(f"Error al crear política de cartera: {e}")
            return False

    def update_politica_cartera(self, politica: PoliticasCartera) -> bool:
        try:
            payload = {
                'descripcion': politica.descripcion,
                'updated_at': datetime.now().isoformat()
            }
            resp = self.supabase.table('politicas_cartera').update(payload).eq('id', politica.id).execute()
            return bool(resp.data)
        except Exception as e:
            print(f"Error al actualizar política de cartera: {e}")
            return False

    def delete_politica_cartera(self, politica_id: int) -> bool:
        try:
            resp = self.supabase.table('politicas_cartera').delete().eq('id', politica_id).execute()
            return bool(resp.data)
        except Exception as e:
            print(f"Error al eliminar política de cartera: {e}")
            return False

    # ============================
    #  Gestión de Comerciales (perfiles)
    # ============================
    def get_comerciales_by_role_id(self, role_id: str) -> List[Dict[str, Any]]:
        """Obtiene perfiles que pertenecen al rol de comercial especificado por role_id."""
        try:
            # Asumimos tabla 'perfiles' con columnas: id(uuid), nombre, email, celular(int), rol_id(uuid), updated_at
            resp = self.supabase.table('perfiles').select('id,nombre,email,celular,rol_id,updated_at').eq('rol_id', role_id).order('updated_at', desc=True).execute()
            return resp.data or []
        except Exception as e:
            print(f"Error al obtener comerciales: {e}")
            return []

    def create_comercial(self, nombre: str, email: Optional[str], celular: Optional[int], role_id: str) -> bool:
        try:
            payload = {
                'nombre': nombre,
                'email': email,
                'celular': celular,
                'rol_id': role_id,
            }
            resp = self.supabase.table('perfiles').insert(payload).execute()
            return bool(resp.data)
        except Exception as e:
            print(f"Error al crear comercial: {e}")
            return False

    def update_comercial(self, perfil_id: str, nombre: str, email: Optional[str], celular: Optional[int]) -> bool:
        try:
            payload = {
                'nombre': nombre,
                'email': email,
                'celular': celular,
                'updated_at': datetime.now().isoformat()
            }
            resp = self.supabase.table('perfiles').update(payload).eq('id', perfil_id).execute()
            return bool(resp.data)
        except Exception as e:
            print(f"Error al actualizar comercial: {e}")
            return False

    def delete_comercial(self, perfil_id: str) -> bool:
        try:
            resp = self.supabase.table('perfiles').delete().eq('id', perfil_id).execute()
            return bool(resp.data)
        except Exception as e:
            print(f"Error al eliminar comercial: {e}")
            return False
                
            # Formatear los datos para que coincidan con la estructura esperada por generar_informe_tecnico_markdown
            datos_calculo = {
                'valor_material': calculos.get('valor_material', 0.0),
                'valor_acabado': calculos.get('valor_acabado', 0.0),
                'valor_troquel': calculos.get('valor_troquel', 0.0),
                'valor_plancha': calculos.get('valor_plancha', 0.0),
                'valor_plancha_separado': calculos.get('valor_plancha_separado'),
                'unidad_z_dientes': calculos.get('unidad_z_dientes', 0),
                'existe_troquel': calculos.get('existe_troquel', False),
                'planchas_x_separado': calculos.get('planchas_x_separado', False),
                'rentabilidad': calculos.get('rentabilidad', 0.0),
                'avance': calculos.get('avance', 0.0),
                'ancho': calculos.get('ancho', 0.0),
                'num_tintas': calculos.get('num_tintas', 0),
                'numero_pistas': calculos.get('numero_pistas', 1),
                'num_paquetes_rollos': calculos.get('num_paquetes_rollos', 0)
            }
            
            return datos_calculo
            
        except Exception as e:
            print(f"Error al obtener cálculos persistidos: {e}")
            traceback.print_exc()
            return None

    def obtener_cotizacion(self, cotizacion_id: int) -> Optional[Cotizacion]:
        """
        Obtiene un objeto Cotizacion completo por su ID usando la RPC get_full_cotizacion_details,
        y luego poblando el objeto con sus relaciones y escalas.
        Respeta RLS a través de la RPC subyacente.
        
        Args:
            cotizacion_id (int): ID de la cotización.
            
        Returns:
            Optional[Cotizacion]: El objeto Cotizacion completo o None.
        """
        print(f"-- Ejecutando obtener_cotizacion para ID: {cotizacion_id} --") # DEBUG
        try:
            # 1. Obtener los detalles planos usando la RPC via get_full_cotizacion_details
            details = self.get_full_cotizacion_details(cotizacion_id)

            if not details:
                print(f"obtener_cotizacion: No se encontraron detalles vía RPC para ID {cotizacion_id}. Retornando None.") # DEBUG
                return None
                    
            print(f"obtener_cotizacion: Detalles RPC obtenidos para ID {cotizacion_id}. Procesando...") # DEBUG
            
            # --- INICIO DIAGNÓSTICO: Mostrar todos los campos ---
            print(f"DIAGNÓSTICO COMPLETO - Todos los campos en details:")
            for k, v in details.items():
                print(f"  {k}: {v} (tipo: {type(v).__name__})")
            # --- FIN DIAGNÓSTICO ---
            
            # 2. Crear objetos relacionados a partir del diccionario `details`
            # Nota: Los nombres de las claves en `details` deben coincidir con los alias en la RPC SQL.
            cliente_obj = None
            if details.get('cliente_id'):
                try:
                    cliente_obj = Cliente(
                        id=details['cliente_id'],
                        nombre=details.get('cliente_nombre'),
                        codigo=details.get('cliente_codigo'),
                        persona_contacto=details.get('cliente_persona_contacto'),
                        correo_electronico=details.get('cliente_correo_electronico'),
                        telefono=details.get('cliente_telefono')
                    )
                except KeyError as ke:
                    print(f"Error creando Cliente: Falta la clave {ke} en detalles RPC")
                    # Podrías retornar None aquí o continuar sin cliente
                except Exception as e_cli:
                    print(f"Error inesperado creando Cliente: {e_cli}")

            # --- INICIO MODIFICACIÓN PERFIL COMERCIAL ---
            perfil_obj = None # Perfil es solo un dict simple aquí
            comercial_id_from_details = details.get('comercial_id') # Asume que RPC devuelve 'comercial_id'
            
            if comercial_id_from_details:
                comercial_nombre_from_details = details.get('comercial_nombre') # Asume que RPC devuelve 'comercial_nombre'
                comercial_email = None # Valor por defecto
                comercial_celular = None # Valor por defecto

                # Intentar buscar email y celular en la tabla perfiles
                print(f"obtener_cotizacion: Buscando email y celular para comercial ID {comercial_id_from_details}...")
                try:
                    perfil_lookup = self.supabase.table('perfiles')\
                        .select('email, celular')\
                        .eq('id', comercial_id_from_details)\
                        .maybe_single().execute()
                    
                    if perfil_lookup.data:
                        comercial_email = perfil_lookup.data.get('email')
                        comercial_celular = perfil_lookup.data.get('celular')
                        print(f"obtener_cotizacion: Datos encontrados - Email: {comercial_email}, Celular: {comercial_celular}")
                    else:
                        print(f"obtener_cotizacion: No se encontraron datos de perfil adicionales para ID {comercial_id_from_details}")
                except Exception as lookup_err_perfil:
                     print(f"Error buscando datos de perfil para ID {comercial_id_from_details}: {lookup_err_perfil}")

                # Crear el diccionario perfil_obj con toda la información
                perfil_obj = {
                    'id': comercial_id_from_details,
                    'nombre': comercial_nombre_from_details,
                    'email': comercial_email, # Añadir email
                    'celular': comercial_celular # Añadir celular
                }
            # --- FIN MODIFICACIÓN PERFIL COMERCIAL ---

            referencia_obj = None
            if details.get('referencia_cliente_id'):
                try:
                    referencia_obj = ReferenciaCliente(
                        id=details['referencia_cliente_id'],
                        cliente_id=details.get('cliente_id'),
                        descripcion=details.get('referencia_descripcion'),
                        id_usuario=details.get('comercial_id'),
                        # creado_en/actualizado_en podrían venir de la RPC si se añadieron
                        # cliente y perfil se asignan después de crear el objeto
                    )
                    referencia_obj.cliente = cliente_obj
                    referencia_obj.perfil = perfil_obj
                except KeyError as ke:
                    print(f"Error creando ReferenciaCliente: Falta la clave {ke} en detalles RPC")
                except Exception as e_ref:
                    print(f"Error inesperado creando ReferenciaCliente: {e_ref}")

            material_obj = None
            # La RPC devuelve material_id y adhesivo_id, podríamos usarlos para obtener los objetos
            # O si la RPC ya devuelve el nombre/valor, usarlos directamente
            if details.get('material_id'):
                material_obj = Material(id=details['material_id'], nombre=details.get('material_nombre', 'N/A')) # Simplificado
                # Si necesitas el valor u otros campos, la RPC debería devolverlos o hacer otra consulta
                
            adhesivo_obj = None # La RPC devuelve adhesivo_id, podríamos obtener objeto si fuera necesario
            if details.get('adhesivo_id'):
                 adhesivo_obj = Adhesivo(id=details['adhesivo_id'], tipo=details.get('adhesivo_tipo', 'N/A')) # Simplificado
                 
            # Crear objeto MaterialAdhesivo (aunque Cotizacion solo guarda el ID)
            # Esto es más para completar la información si se necesitara
            material_adhesivo_obj = None
            if details.get('material_adhesivo_id'):
                 material_adhesivo_obj = { # Usar un dict simple ya que no hay modelo específico
                      'id': details['material_adhesivo_id'],
                      'material_id': details.get('material_id'),
                      'adhesivo_id': details.get('adhesivo_id'),
                      'valor': details.get('material_valor') # Asumiendo que la RPC devuelve el valor usado
                 }

            # --- INICIO MODIFICACIÓN ACABADO ---
            acabado_obj = None
            acabado_id_from_details = details.get('acabado_id') # Obtener ID del acabado

            if acabado_id_from_details:
                acabado_nombre_from_details = details.get('acabado_nombre') # Obtener nombre si la RPC lo provee

                # Si el nombre no vino de la RPC (o es 'N/A'), intentar buscarlo por ID
                if not acabado_nombre_from_details or acabado_nombre_from_details == 'N/A':
                    print(f"obtener_cotizacion: Acabado nombre no encontrado en details (o es 'N/A'). Intentando buscar por ID {acabado_id_from_details}...")
                    try:
                        acabado_lookup_response = self.supabase.table('acabados').select('nombre').eq('id', acabado_id_from_details).maybe_single().execute()
                        if acabado_lookup_response.data and acabado_lookup_response.data.get('nombre'):
                            acabado_nombre_from_details = acabado_lookup_response.data['nombre']
                            print(f"obtener_cotizacion: Nombre de acabado encontrado por lookup: {acabado_nombre_from_details}")
                        else:
                             print(f"obtener_cotizacion: No se encontró nombre de acabado en lookup para ID {acabado_id_from_details}")
                             acabado_nombre_from_details = 'N/A' # Mantener N/A si la búsqueda falla
                    except Exception as lookup_err:
                         print(f"Error buscando nombre de acabado por ID {acabado_id_from_details}: {lookup_err}")
                         acabado_nombre_from_details = 'N/A' # Mantener N/A en caso de error

                # Intentar crear el objeto Acabado con el ID y el nombre (obtenido de RPC o lookup)
                try:
                    acabado_obj = Acabado(id=acabado_id_from_details, nombre=acabado_nombre_from_details)
                except Exception as e_acab:
                     print(f"Error creando objeto Acabado con ID {acabado_id_from_details} y Nombre {acabado_nombre_from_details}: {e_acab}")
                     # acabado_obj permanecerá como None si falla la creación
            # --- FIN MODIFICACIÓN ACABADO ---
            
            tipo_prod_obj = None
            if details.get('tipo_producto_id'):
                tipo_prod_obj = TipoProducto(id=details['tipo_producto_id'], nombre=details.get('tipo_producto_nombre', 'N/A')) # Simplificado
                

                 
            tipo_grafado_obj = None # El modelo Cotizacion usa tipo_grafado_id directamente
            if details.get('tipo_grafado_id'):
                 tipo_grafado_obj = TipoGrafado(id=details['tipo_grafado_id'], nombre=details.get('tipo_grafado_nombre', 'N/A')) # Simplificado

            # 3. Crear el objeto Cotizacion principal
            cotizacion = Cotizacion(
                id=cotizacion_id,
                # IDs (directamente de `details`)
                referencia_cliente_id=details.get('referencia_cliente_id'),
                material_adhesivo_id=details.get('material_adhesivo_id'), # Guardamos el ID de la tabla combinada
                acabado_id=details.get('acabado_id'),
                tipo_foil_id=details.get('tipo_foil_id'),  # Agregado campo tipo_foil_id
                tipo_producto_id=details.get('tipo_producto_id'),
                tipo_grafado_id=details.get('tipo_grafado_id'),
                estado_id=details.get('estado_id'),
                id_motivo_rechazo=details.get('id_motivo_rechazo'),
                # Campos directos de `details` (asegurar que la RPC los devuelve)
                numero_cotizacion=details.get('numero_cotizacion'),
                num_tintas=details.get('num_tintas'),
                num_paquetes_rollos=details.get('num_paquetes_rollos'),
                es_manga=details.get('es_manga', False),
                valor_troquel=details.get('valor_troquel'),
                valor_plancha_separado=details.get('valor_plancha_separado'),
                planchas_x_separado=details.get('planchas_x_separado', False),
                existe_troquel=details.get('existe_troquel', False),
                numero_pistas=details.get('numero_pistas', 1), # Usar el valor de details si la RPC lo devuelve
                ancho=details.get('ancho'),
                avance=details.get('avance'),
                fecha_creacion=details.get('fecha_creacion'),
                identificador=details.get('identificador'),
                es_recotizacion=details.get('es_recotizacion', False),
                altura_grafado=details.get('altura_grafado'),
                # Campos de auditoría
                modificado_por=details.get('modificado_por'),
                actualizado_en=details.get('actualizado_en'), # Corregido: usar actualizado_en
                # Objetos relacionados (creados arriba)
                referencia_cliente=referencia_obj,
                material_adhesivo=material_adhesivo_obj, # Pasar el dict simple
                # Los siguientes son opcionales para el objeto Cotizacion si no se usan directamente
                # material=material_obj, 
                # adhesivo=adhesivo_obj,
                acabado=acabado_obj,
                tipo_producto=tipo_prod_obj,
                tipo_foil=TipoFoil(id=details.get('tipo_foil_id'), nombre=details.get('tipo_foil_nombre', 'N/A')) if details.get('tipo_foil_id') else None,  # Agregado objeto tipo_foil
                # tipo_grafado=tipo_grafado_obj, # ID es suficiente
            )
            
            print(f"obtener_cotizacion: Objeto Cotizacion creado para ID {cotizacion_id}") # DEBUG

            # 4. Obtener y asignar las escalas
            print(f"obtener_cotizacion: Obteniendo escalas para ID {cotizacion_id}...") # DEBUG
            cotizacion.escalas = self.get_cotizacion_escalas(cotizacion.id)
            print(f"obtener_cotizacion: {len(cotizacion.escalas)} escalas asignadas.") # DEBUG
                
            print(f"-- Fin obtener_cotizacion (Éxito) para ID: {cotizacion_id} --") # DEBUG
            return cotizacion
                
        except KeyError as ke:
            print(f"Error fatal en obtener_cotizacion (KeyError): Falta la clave {ke} en los detalles de la RPC.")
            traceback.print_exc()
            return None
        except Exception as e:
            print(f"Error inesperado en obtener_cotizacion para ID {cotizacion_id}: {e}")
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
            select_query = 'id, numero_cotizacion, fecha_creacion, estado_id, ajustes_modificados_admin'
            
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
                            'estado_id': cotizacion.get('estado_id'),
                            'ajustes_modificados_admin': cotizacion.get('ajustes_modificados_admin', False)  # AÑADIDO: Asegura que el flag se incluya en los datos
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
        Ahora usa una función RPC dedicada que evita problemas con RLS.
        
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
            
            # Usar la función RPC dedicada para actualizar el estado (bypass RLS)
            response = self.supabase.rpc(
                'update_estado_cotizacion',
                {
                    'p_cotizacion_id': cotizacion_id,
                    'p_estado_id': estado_id,
                    'p_id_motivo_rechazo': id_motivo_rechazo
                }
            ).execute()
            
            if response.data is None or (isinstance(response.data, bool) and not response.data):
                print("Error al actualizar el estado a través de RPC")
                print(f"Respuesta: {response.data}")
                if hasattr(response, 'error') and response.error:
                    print(f"Error: {response.error}")
                return False
            
            print(f"Estado actualizado exitosamente vía RPC")
            return True
            
        except Exception as e:
            print(f"Error al actualizar estado de cotización: {str(e)}")
            traceback.print_exc()
            return False

    # --- NUEVO: Función para obtener descripción de forma de pago --- 


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

    # --- New Methods ---

    def get_adhesivos(self) -> List[Adhesivo]:
        """Obtiene todos los adhesivos disponibles."""
        def _operation():
            try:
                # ADD DEBUG LOGGING HERE
                print("--- DEBUG: Inside get_adhesivos._operation ---")
                response = self.supabase.table('adhesivos').select('*').execute()
                # ADD MORE DEBUG LOGGING HERE
                print(f"--- DEBUG: Raw response from adhesivos: {response.data}")
                if response.data:
                    # Assuming Adhesivo model exists and matches table structure
                    adhesivos_list = [Adhesivo(**data) for data in response.data]
                    print(f"--- DEBUG: Parsed Adhesivos list: {adhesivos_list}") # Log the parsed list
                    return adhesivos_list
                print("--- DEBUG: No data found in adhesivos response.")
                return []
            except Exception as e:
                print(f"--- DEBUG: Exception in get_adhesivos._operation: {e}") # Log exception
                print(f"Error fetching adhesivos: {e}")
                logging.error(f"Error fetching adhesivos: {e}", exc_info=True)
                return None # Return None to trigger retry

        result = self._retry_operation("fetching adhesivos", _operation)
        print(f"--- DEBUG: Final result from get_adhesivos (after retry): {result}") # Log final result
        return result if result is not None else []

    def get_material_adhesivo_valor(self, material_id: int, adhesivo_id: int) -> Optional[float]:
        """
        Obtiene el valor (precio) de la combinación específica de material y adhesivo.

        Args:
            material_id: ID del material.
            adhesivo_id: ID del adhesivo.

        Returns:
            El valor como float si se encuentra, None en caso contrario o si hay error.
        """
        def _operation():
            try:
                print(f"Querying material_adhesivo for material_id={material_id}, adhesivo_id={adhesivo_id}")
                # Corrected query chaining without backslashes
                response = (self.supabase.table('material_adhesivo')
                    .select('valor')
                    .eq('material_id', material_id)
                    .eq('adhesivo_id', adhesivo_id)
                    .limit(1)
                    .execute())

                if response.data:
                    valor = response.data[0].get('valor')
                    print(f"Found valor: {valor}")
                    # Ensure conversion to float handles potential DB types
                    return float(valor) if valor is not None else None
                else:
                    print("No matching material_adhesivo found.")
                    return None # No combination found
            except Exception as e:
                print(f"Error fetching material_adhesivo valor: {e}")
                logging.error(f"Error fetching material_adhesivo valor for material={material_id}, adhesivo={adhesivo_id}: {e}", exc_info=True)
                # Return None on error to allow retry or indicate failure
                return None

        # Retry the operation
        result = self._retry_operation(f"fetching material_adhesivo valor ({material_id}/{adhesivo_id})", _operation)
        # Return the result (float or None if not found/error after retries)
        return result

    def get_adhesivos_for_material(self, material_id: int) -> List[Adhesivo]:
        """
        Obtiene la lista de adhesivos disponibles para un material específico.

        Args:
            material_id: ID del material.

        Returns:
            Lista de objetos Adhesivo compatibles.
        """
        if material_id is None:
            return []

        def _operation():
            try:
                # Query material_adhesivo, join with adhesivos, filter by material_id
                response = (self.supabase.table('material_adhesivo')
                    .select('adhesivos(*)') # Select all columns from the joined adhesivos table
                    .eq('material_id', material_id)
                    .execute())
                
                adhesivos_compatibles = []
                if response.data:
                    # The result is a list of dicts like: [{'adhesivos': {'id': 1, 'tipo': '...', ...}}, ...]
                    for item in response.data:
                        adhesivo_data = item.get('adhesivos')
                        if adhesivo_data:
                            try:
                                # REMOVED: Ensure 'Sin adhesivo' is not included in the selectable options for etiquetas
                                # if adhesivo_data.get('tipo') != 'Sin adhesivo': 
                                adhesivos_compatibles.append(Adhesivo(**adhesivo_data))
                            except TypeError as te:
                                print(f"Error creating Adhesivo object from data: {adhesivo_data}, Error: {te}")
                
                print(f"--- DEBUG: Found {len(adhesivos_compatibles)} compatible adhesivos for material {material_id}")
                return adhesivos_compatibles
            except Exception as e:
                print(f"Error fetching compatible adhesivos for material {material_id}: {e}")
                logging.error(f"Error fetching compatible adhesivos for material {material_id}: {e}", exc_info=True)
                return None # Return None to trigger retry

        result = self._retry_operation(f"fetching compatible adhesivos for material {material_id}", _operation)
        return result if result is not None else []

    # --- NUEVO MÉTODO HELPER ---
    def get_material_id_from_material_adhesivo(self, material_adhesivo_id: int) -> Optional[int]:
        """
        Obtiene el material_id asociado a una entrada específica en la tabla material_adhesivo.

        Args:
            material_adhesivo_id: El ID de la fila en la tabla material_adhesivo.

        Returns:
            El material_id (int) asociado, o None si no se encuentra o hay error.
        """
        def _operation():
            if material_adhesivo_id is None:
                print("Error: material_adhesivo_id es requerido para get_material_id_from_material_adhesivo")
                return None
            try:
                # print(f"Querying material_adhesivo for material_id: entry_id={material_adhesivo_id}") # Optional debug
                response = (self.supabase.table('material_adhesivo')
                    .select('material_id')
                    .eq('id', material_adhesivo_id)
                    .limit(1)
                    .maybe_single() # Use maybe_single as it should be unique
                    .execute())

                # maybe_single returns the dict directly if found, or None
                if response.data:
                    mat_id = response.data.get('material_id')
                    # print(f"Found material_id: {mat_id}") # Optional debug
                    return mat_id
                else:
                    print(f"No material_adhesivo entry found with id {material_adhesivo_id}.")
                    return None
            except Exception as e:
                print(f"Error fetching material_id from material_adhesivo: {e}")
                logging.error(f"Error fetching material_id for material_adhesivo_id={material_adhesivo_id}: {e}", exc_info=True)
                return None

        # No usamos retry aquí porque None es un resultado esperado si el ID no existe.
        try:
             return _operation()
        except Exception as e:
             print(f"Excepción final en get_material_id_from_material_adhesivo: {e}")
             return None
    # --- FIN NUEVO MÉTODO HELPER ---

    # --- NUEVO MÉTODO PARA CÓDIGO DE MATERIAL_ADHESIVO ---
    def get_material_adhesivo_code(self, material_adhesivo_id: int) -> str:
        """
        Obtiene el código directamente desde la tabla material_adhesivo usando su ID.
        Se asume que la columna 'code' existe en 'material_adhesivo'.

        Args:
            material_adhesivo_id: El ID de la fila en la tabla material_adhesivo.

        Returns:
            El código (str) asociado, o una cadena vacía si no se encuentra o hay error.
        """
        if material_adhesivo_id is None:
            return ""
        try:
            response = (self.supabase.table('material_adhesivo')
                .select('code') # Seleccionar la columna 'code' directamente
                .eq('id', material_adhesivo_id)
                .limit(1)
                .maybe_single()
                .execute())

            if response.data and response.data.get('code'):
                return response.data['code']
            else:
                print(f"Advertencia: No se encontró código para material_adhesivo_id {material_adhesivo_id}.")
                return ""
        except Exception as e:
            print(f"Error fetching code from material_adhesivo: {e}")
            logging.error(f"Error fetching code for material_adhesivo_id={material_adhesivo_id}: {e}", exc_info=True)
            return ""
    # --- FIN NUEVO MÉTODO ---

    def get_adhesivos_for_material(self, material_id: int) -> List[Adhesivo]:
        """
        Obtiene la lista de adhesivos disponibles para un material específico.

        Args:
            material_id: ID del material.

        Returns:
            Lista de objetos Adhesivo compatibles.
        """
        if material_id is None:
            return []

        def _operation():
            try:
                # Query material_adhesivo, join with adhesivos, filter by material_id
                response = (self.supabase.table('material_adhesivo')
                    .select('adhesivos(*)') # Select all columns from the joined adhesivos table
                    .eq('material_id', material_id)
                    .execute())
                
                adhesivos_compatibles = []
                if response.data:
                    # The result is a list of dicts like: [{'adhesivos': {'id': 1, 'tipo': '...', ...}}, ...]
                    for item in response.data:
                        adhesivo_data = item.get('adhesivos')
                        if adhesivo_data:
                            try:
                                # REMOVED: Ensure 'Sin adhesivo' is not included in the selectable options for etiquetas
                                # if adhesivo_data.get('tipo') != 'Sin adhesivo': 
                                adhesivos_compatibles.append(Adhesivo(**adhesivo_data))
                            except TypeError as te:
                                print(f"Error creating Adhesivo object from data: {adhesivo_data}, Error: {te}")
                
                print(f"--- DEBUG: Found {len(adhesivos_compatibles)} compatible adhesivos for material {material_id}")
                return adhesivos_compatibles
            except Exception as e:
                print(f"Error fetching compatible adhesivos for material {material_id}: {e}")
                logging.error(f"Error fetching compatible adhesivos for material {material_id}: {e}", exc_info=True)
                return None # Return None to trigger retry

        result = self._retry_operation(f"fetching compatible adhesivos for material {material_id}", _operation)
        return result if result is not None else []

    def get_all_cotizaciones_overview(self) -> List[Dict[str, Any]]:
        """Recupera una lista simplificada de todas las cotizaciones para la vista de gestión."""
        def _operation():
            try:
                # Llamar a la función RPC get_all_cotizaciones_overview
                response = self.supabase.rpc('get_all_cotizaciones_overview').execute()
                
                # La RPC ya devuelve los datos procesados como una lista de diccionarios
                if response.data:
                    return response.data
                else:
                    return []

            except PostgrestAPIError as e:
                print(f"Error al obtener overview de cotizaciones vía RPC: {e}")
                return []
            except Exception as e:
                print(f"Error inesperado en RPC get_all_cotizaciones_overview: {e}")
                traceback.print_exc()
                return []
        
        return self._retry_operation("get_all_cotizaciones_overview (RPC)", _operation)

    def get_cotizaciones_overview_by_comercial(self, comercial_id: str) -> List[Dict[str, Any]]:
        """Recupera una lista simplificada de cotizaciones para un comercial específico."""
        
        def _operation():
            try:
                # Llamar a la función RPC get_cotizaciones_overview_by_comercial
                response = self.supabase.rpc(
                    'get_cotizaciones_overview_by_comercial',
                    {'p_comercial_id': comercial_id}
                ).execute()
                
                # La RPC ya devuelve los datos procesados como una lista de diccionarios
                if response.data:
                    return response.data
                else:
                    return []
                    
            except PostgrestAPIError as e:
                print(f"Error al obtener overview de cotizaciones por comercial ({comercial_id}) vía RPC: {e}")
                return []
            except Exception as e:
                print(f"Error inesperado en RPC get_cotizaciones_overview_by_comercial ({comercial_id}): {e}")
                traceback.print_exc()
                return []
                
        return self._retry_operation(f"get_cotizaciones_overview_by_comercial (RPC {comercial_id})", _operation)

    def get_full_cotizacion_details(self, cotizacion_id: int) -> Optional[Dict[str, Any]]:
        """
        Recupera todos los detalles de una cotización específica, incluyendo datos relacionados,
        para poder recargar el formulario en modo edición.
        Utiliza una función RPC para mayor eficiencia y robustez.
        """
        print(f"-- DEBUG: Entrando en get_full_cotizacion_details para ID: {cotizacion_id} --")
        rpc_result_data = None
        response_obj = None # Para inspeccionar el objeto response
        try:
            # --- Llamada directa a RPC SIN _retry_operation --- 
            print(f"-- DEBUG: Llamando RPC 'get_cotizacion_details_for_edit' con p_cotizacion_id={cotizacion_id} --")
            
            # --- Bloque try/except específico para la llamada RPC --- 
            try:
                response_obj = self.supabase.rpc(
                    'get_cotizacion_details_for_edit',
                    {'p_cotizacion_id': cotizacion_id}
                ).execute()
                print(f"-- DEBUG: Llamada RPC execute() completada. --")
            except PostgrestAPIError as pg_err:
                print(f"-- ERROR: PostgrestAPIError directo en llamada RPC ({cotizacion_id}): {pg_err.code} - {pg_err.message} --")
                print(f"-- ERROR Details: {pg_err.details} --")
                print(f"-- ERROR Hint: {pg_err.hint} --")
                return None # Error API, retornar None
            except Exception as call_err:
                # Capturar cualquier otro error durante la ejecución de RPC
                print(f"-- ERROR: Excepción directa en llamada RPC ({cotizacion_id}): {type(call_err).__name__} - {call_err} --")
                traceback.print_exc()
                return None # Error inesperado, retornar None
            # ----------------------------------------------------------
            
            # -- Inspeccionar el objeto response --
            print(f"-- DEBUG: Objeto Response RAW recibido: {response_obj} (Tipo: {type(response_obj)}) --")
            if response_obj and hasattr(response_obj, 'data'):
                print(f"-- DEBUG: Atributo response.data: {response_obj.data} (Tipo: {type(response_obj.data)}) --")
                rpc_result_data = response_obj.data
            elif response_obj:
                print("-- WARNING: Objeto response recibido pero no tiene atributo 'data' o es None/False --")
            else:
                print("-- WARNING: El objeto response en sí es None o False después de execute() --")
            # ------------------------------------

            # Verificar si obtuvimos datos válidos (diccionario)
            if rpc_result_data and isinstance(rpc_result_data, dict):
                print(f"-- DEBUG: RPC devolvió datos válidos (diccionario). Retornando... --")
                return rpc_result_data
            elif rpc_result_data:
                print(f"-- WARNING: RPC devolvió datos pero no en formato dict. Tipo: {type(rpc_result_data)} --")
                return None 
            else:
                print(f"-- DEBUG: RPC no devolvió datos válidos (o fue None/False) para ID {cotizacion_id} --")
                return None 
                
        except Exception as outer_err:
            # Error fuera de la llamada RPC específica pero dentro de la función
            print(f"-- ERROR: Error inesperado en get_full_cotizacion_details ({cotizacion_id}): {type(outer_err).__name__} - {outer_err} --")
            traceback.print_exc()
            return None

    # --- Funciones para Edición --- 
    def obtener_cotizacion(self, cotizacion_id: int) -> Optional[Cotizacion]:
        """
        Obtiene un objeto Cotizacion completo por su ID usando la RPC get_full_cotizacion_details,
        y luego poblando el objeto con sus relaciones y escalas.
        Respeta RLS a través de la RPC subyacente.

        Args:
            cotizacion_id (int): ID de la cotización.

        Returns:
            Optional[Cotizacion]: El objeto Cotizacion completo o None.
        """
        print(f"-- Ejecutando obtener_cotizacion para ID: {cotizacion_id} --") # DEBUG
        try:
            # 1. Obtener los detalles planos usando la RPC via get_full_cotizacion_details
            details = self.get_full_cotizacion_details(cotizacion_id)

            if not details:
                print(f"obtener_cotizacion: No se encontraron detalles vía RPC para ID {cotizacion_id}. Retornando None.") # DEBUG
                return None

            print(f"obtener_cotizacion: Detalles RPC obtenidos para ID {cotizacion_id}. Procesando...") # DEBUG
            # print(f"Detalles RPC: {details}") # DEBUG detallado opcional
            
            # 2. Crear objetos relacionados a partir del diccionario `details`
            # Nota: Los nombres de las claves en `details` deben coincidir con los alias en la RPC SQL.
            cliente_obj = None
            if details.get('cliente_id'):
                try:
                    cliente_obj = Cliente(
                        id=details['cliente_id'],
                        nombre=details.get('cliente_nombre'),
                        codigo=details.get('cliente_codigo'),
                        persona_contacto=details.get('cliente_persona_contacto'),
                        correo_electronico=details.get('cliente_correo_electronico'),
                        telefono=details.get('cliente_telefono')
                    )
                except KeyError as ke:
                    print(f"Error creando Cliente: Falta la clave {ke} en detalles RPC")
                    # Podrías retornar None aquí o continuar sin cliente
                except Exception as e_cli:
                    print(f"Error inesperado creando Cliente: {e_cli}")

            # --- INICIO MODIFICACIÓN PERFIL COMERCIAL ---
            perfil_obj = None # Perfil es solo un dict simple aquí
            comercial_id_from_details = details.get('comercial_id') # Asume que RPC devuelve 'comercial_id'
            
            if comercial_id_from_details:
                comercial_nombre_from_details = details.get('comercial_nombre') # Asume que RPC devuelve 'comercial_nombre'
                comercial_email = None # Valor por defecto
                comercial_celular = None # Valor por defecto

                # Intentar buscar email y celular en la tabla perfiles
                print(f"obtener_cotizacion: Buscando email y celular para comercial ID {comercial_id_from_details}...")
                try:
                    perfil_lookup = self.supabase.table('perfiles')\
                        .select('email, celular')\
                        .eq('id', comercial_id_from_details)\
                        .maybe_single().execute()
                    
                    if perfil_lookup.data:
                        comercial_email = perfil_lookup.data.get('email')
                        comercial_celular = perfil_lookup.data.get('celular')
                except Exception as lookup_err_perfil:
                     print(f"Error buscando datos de perfil para ID {comercial_id_from_details}: {lookup_err_perfil}")

                # Crear el diccionario perfil_obj con toda la información
                perfil_obj = {
                    'id': comercial_id_from_details,
                    'nombre': comercial_nombre_from_details,
                    'email': comercial_email, # Añadir email
                    'celular': comercial_celular # Añadir celular
                }
            # --- FIN MODIFICACIÓN PERFIL COMERCIAL ---

            referencia_obj = None
            if details.get('referencia_cliente_id'):
                try:
                    referencia_obj = ReferenciaCliente(
                        id=details['referencia_cliente_id'],
                        cliente_id=details.get('cliente_id'),
                        descripcion=details.get('referencia_descripcion'),
                        id_usuario=details.get('comercial_id'),
                        # creado_en/actualizado_en podrían venir de la RPC si se añadieron
                        # cliente y perfil se asignan después de crear el objeto
                    )
                    referencia_obj.cliente = cliente_obj
                    referencia_obj.perfil = perfil_obj
                except KeyError as ke:
                    print(f"Error creando ReferenciaCliente: Falta la clave {ke} en detalles RPC")
                except Exception as e_ref:
                    print(f"Error inesperado creando ReferenciaCliente: {e_ref}")

            material_obj = None
            # La RPC devuelve material_id y adhesivo_id, podríamos usarlos para obtener los objetos
            # O si la RPC ya devuelve el nombre/valor, usarlos directamente
            if details.get('material_id'):
                material_obj = Material(id=details['material_id'], nombre=details.get('material_nombre', 'N/A')) # Simplificado
                # Si necesitas el valor u otros campos, la RPC debería devolverlos o hacer otra consulta
                
            adhesivo_obj = None # La RPC devuelve adhesivo_id, podríamos obtener objeto si fuera necesario
            if details.get('adhesivo_id'):
                 adhesivo_obj = Adhesivo(id=details['adhesivo_id'], tipo=details.get('adhesivo_tipo', 'N/A')) # Simplificado
                 
            # Crear objeto MaterialAdhesivo (aunque Cotizacion solo guarda el ID)
            # Esto es más para completar la información si se necesitara
            material_adhesivo_obj = None
            if details.get('material_adhesivo_id'):
                 material_adhesivo_obj = { # Usar un dict simple ya que no hay modelo específico
                      'id': details['material_adhesivo_id'],
                      'material_id': details.get('material_id'),
                      'adhesivo_id': details.get('adhesivo_id'),
                      'valor': details.get('material_valor') # Asumiendo que la RPC devuelve el valor usado
                 }

            # --- INICIO MODIFICACIÓN ACABADO ---
            acabado_obj = None
            acabado_id_from_details = details.get('acabado_id') # Obtener ID del acabado

            if acabado_id_from_details:
                acabado_nombre_from_details = details.get('acabado_nombre') # Obtener nombre si la RPC lo provee

                # Si el nombre no vino de la RPC (o es 'N/A'), intentar buscarlo por ID
                if not acabado_nombre_from_details or acabado_nombre_from_details == 'N/A':
                    print(f"obtener_cotizacion: Acabado nombre no encontrado en details (o es 'N/A'). Intentando buscar por ID {acabado_id_from_details}...")
                    try:
                        acabado_lookup_response = self.supabase.table('acabados').select('nombre').eq('id', acabado_id_from_details).maybe_single().execute()
                        if acabado_lookup_response.data and acabado_lookup_response.data.get('nombre'):
                            acabado_nombre_from_details = acabado_lookup_response.data['nombre']
                            print(f"obtener_cotizacion: Nombre de acabado encontrado por lookup: {acabado_nombre_from_details}")
                        else:
                             print(f"obtener_cotizacion: No se encontró nombre de acabado en lookup para ID {acabado_id_from_details}")
                             acabado_nombre_from_details = 'N/A' # Mantener N/A si la búsqueda falla
                    except Exception as lookup_err:
                         print(f"Error buscando nombre de acabado por ID {acabado_id_from_details}: {lookup_err}")
                         acabado_nombre_from_details = 'N/A' # Mantener N/A en caso de error

                # Intentar crear el objeto Acabado con el ID y el nombre (obtenido de RPC o lookup)
                try:
                    acabado_obj = Acabado(id=acabado_id_from_details, nombre=acabado_nombre_from_details)
                except Exception as e_acab:
                     print(f"Error creando objeto Acabado con ID {acabado_id_from_details} y Nombre {acabado_nombre_from_details}: {e_acab}")
                     # acabado_obj permanecerá como None si falla la creación
            # --- FIN MODIFICACIÓN ACABADO ---
            
            tipo_prod_obj = None
            if details.get('tipo_producto_id'):
                tipo_prod_obj = TipoProducto(id=details['tipo_producto_id'], nombre=details.get('tipo_producto_nombre', 'N/A')) # Simplificado
                

                 
            tipo_grafado_obj = None # El modelo Cotizacion usa tipo_grafado_id directamente
            if details.get('tipo_grafado_id'):
                 tipo_grafado_obj = TipoGrafado(id=details['tipo_grafado_id'], nombre=details.get('tipo_grafado_nombre', 'N/A')) # Simplificado

            # 3. Crear el objeto Cotizacion principal
            cotizacion = Cotizacion(
                id=cotizacion_id,
                # IDs (directamente de `details`)
                referencia_cliente_id=details.get('referencia_cliente_id'),
                material_adhesivo_id=details.get('material_adhesivo_id'), # Guardamos el ID de la tabla combinada
                acabado_id=details.get('acabado_id'),
                tipo_foil_id=details.get('tipo_foil_id'),  # Agregado campo tipo_foil_id
                tipo_producto_id=details.get('tipo_producto_id'),
                tipo_grafado_id=details.get('tipo_grafado_id'),
                estado_id=details.get('estado_id'),
                id_motivo_rechazo=details.get('id_motivo_rechazo'),
                # Campos directos de `details` (asegurar que la RPC los devuelve)
                numero_cotizacion=details.get('numero_cotizacion'),
                num_tintas=details.get('num_tintas'),
                num_paquetes_rollos=details.get('num_paquetes_rollos'),
                es_manga=details.get('es_manga', False),
                valor_troquel=details.get('valor_troquel'),
                valor_plancha_separado=details.get('valor_plancha_separado'),
                planchas_x_separado=details.get('planchas_x_separado', False),
                existe_troquel=details.get('existe_troquel', False),
                numero_pistas=details.get('numero_pistas', 1), # Usar el valor de details si la RPC lo devuelve
                ancho=details.get('ancho'),
                avance=details.get('avance'),
                fecha_creacion=details.get('fecha_creacion'),
                identificador=details.get('identificador'),
                es_recotizacion=details.get('es_recotizacion', False),
                altura_grafado=details.get('altura_grafado'),
                # Campos de auditoría
                modificado_por=details.get('modificado_por'),
                actualizado_en=details.get('actualizado_en'), # Corregido: usar actualizado_en
                # Objetos relacionados (creados arriba)
                referencia_cliente=referencia_obj,
                material_adhesivo=material_adhesivo_obj, # Pasar el dict simple
                # Los siguientes son opcionales para el objeto Cotizacion si no se usan directamente
                # material=material_obj, 
                # adhesivo=adhesivo_obj,
                acabado=acabado_obj,
                tipo_producto=tipo_prod_obj,
                tipo_foil=TipoFoil(id=details.get('tipo_foil_id'), nombre=details.get('tipo_foil_nombre', 'N/A')) if details.get('tipo_foil_id') else None,  # Agregado objeto tipo_foil
                # tipo_grafado=tipo_grafado_obj, # ID es suficiente
            )
            
            print(f"obtener_cotizacion: Objeto Cotizacion creado para ID {cotizacion_id}") # DEBUG

            # 4. Obtener y asignar las escalas
            print(f"obtener_cotizacion: Obteniendo escalas para ID {cotizacion_id}...") # DEBUG
            cotizacion.escalas = self.get_cotizacion_escalas(cotizacion.id)
            print(f"obtener_cotizacion: {len(cotizacion.escalas)} escalas asignadas.") # DEBUG
            
            print(f"-- Fin obtener_cotizacion (Éxito) para ID: {cotizacion_id} --") # DEBUG
            return cotizacion

        except KeyError as ke:
            print(f"Error fatal en obtener_cotizacion (KeyError): Falta la clave {ke} en los detalles de la RPC.")
            traceback.print_exc()
            return None
        except Exception as e:
            print(f"Error inesperado en obtener_cotizacion para ID {cotizacion_id}: {e}")
            traceback.print_exc()
            return None

    def update_referencia_cliente(self, referencia_id: int, data: Dict[str, Any]) -> bool:
        """Actualiza campos específicos de una referencia cliente."""
        # TODO: Implementar query de actualización para la tabla referencia_cliente
        print(f"Placeholder: update_referencia_cliente called for ID {referencia_id} with data: {data}")
        try:
            # Ejemplo:
            # self.supabase.from_('referencia_cliente').update(data).eq('id', referencia_id).execute()
            # Verificar si la actualización fue exitosa (puede requerir chequear el resultado)
            return True # Asumir éxito por ahora
        except Exception as e:
            print(f"Error actualizando referencia_cliente ID {referencia_id}: {e}")
            return False

    def eliminar_calculos_escala(self, cotizacion_id: int) -> bool:
        """Elimina los registros de calculos_escala_cotizacion asociados a una cotización."""
        # TODO: Implementar query de eliminación
        print(f"Placeholder: eliminar_calculos_escala called for cotizacion_id {cotizacion_id}")
        try:
            # Ejemplo:
            # self.supabase.from_('calculos_escala_cotizacion').delete().eq('cotizacion_id', cotizacion_id).execute()
            return True # Asumir éxito
        except Exception as e:
            print(f"Error eliminando calculos_escala_cotizacion para cotizacion_id {cotizacion_id}: {e}")
            return False

    def eliminar_cotizacion_escalas(self, cotizacion_id: int) -> bool:
        """Elimina los registros de cotizacion_escalas asociados a una cotización."""
        # TODO: Implementar query de eliminación
        print(f"Placeholder: eliminar_cotizacion_escalas called for cotizacion_id {cotizacion_id}")
        try:
            # Ejemplo:
            # self.supabase.from_('cotizacion_escalas').delete().eq('cotizacion_id', cotizacion_id).execute()
            # Considerar eliminar precios_escala también si no se hace en cascada
            # self.supabase.rpc('eliminar_escalas_y_precios', {'p_cotizacion_id': cotizacion_id})
            return True # Asumir éxito
        except Exception as e:
            print(f"Error eliminando cotizacion_escalas para cotizacion_id {cotizacion_id}: {e}")
            return False
    # --- Fin Funciones para Edición ---

    # --- INICIO NUEVA FUNCIÓN ---
    def get_adhesivo_id_from_material_adhesivo(self, material_adhesivo_id: int) -> Optional[int]:
        """
        Obtiene el adhesivo_id asociado a una entrada específica en la tabla material_adhesivo.

        Args:
            material_adhesivo_id: El ID de la fila en la tabla material_adhesivo.

        Returns:
            El adhesivo_id (int) asociado, o None si no se encuentra o hay error.
        """
        def _operation():
            if material_adhesivo_id is None:
                print("Error: material_adhesivo_id es requerido para get_adhesivo_id_from_material_adhesivo")
                return None
            try:
                # print(f"Querying material_adhesivo for adhesivo_id: entry_id={material_adhesivo_id}") # Optional debug
                response = (self.supabase.table('material_adhesivo') # <-- Sin escapes
                    .select('adhesivo_id') # Seleccionar adhesivo_id
                    .eq('id', material_adhesivo_id)
                    .limit(1)
                    .maybe_single() # Use maybe_single as it should be unique
                    .execute())

                # maybe_single returns the dict directly if found, or None
                if response.data:
                    adh_id = response.data.get('adhesivo_id')
                    # print(f"Found adhesivo_id: {adh_id}") # Optional debug
                    return adh_id
                else:
                    print(f"No material_adhesivo entry found with id {material_adhesivo_id}.")
                    return None
            except Exception as e:
                print(f"Error fetching adhesivo_id from material_adhesivo: {e}")
                logging.error(f"Error fetching adhesivo_id for material_adhesivo_id={material_adhesivo_id}: {e}", exc_info=True)
                return None

        # No usamos retry aquí porque None es un resultado esperado si el ID no existe.
        try:
             return _operation()
        except Exception as e:
             print(f"Excepción final en get_adhesivo_id_from_material_adhesivo: {e}")
             return None
    # --- FIN NUEVA FUNCIÓN ---

    # --- NUEVA FUNCIÓN: Verificar existencia de identificador --- 
    def check_identificador_exists(self, identificador: str, exclude_cotizacion_id: int) -> bool:
        """Verifica si un identificador ya existe para otra cotización."""
        if not identificador:
            return False # No verificar si el identificador está vacío
        try:
            response = self.supabase.rpc(
                'check_identificador_exists', 
                {'p_identificador': identificador, 'p_exclude_id': exclude_cotizacion_id}
            ).execute()
            # La RPC devuelve true si existe, false si no
            return response.data if isinstance(response.data, bool) else False
        except Exception as e:
            print(f"Error verificando identificador '{identificador}' (excluyendo {exclude_cotizacion_id}): {e}")
            # En caso de error, es más seguro asumir que SÍ existe para evitar duplicados
            return True 

    #@st.cache_data
    def get_adhesivos_for_material(_self, material_id: int) -> List[Adhesivo]:
        """
        Obtiene la lista de adhesivos disponibles para un material específico.
        ... (docstring) ...
        """
        print(f"[CACHE CHECK] get_adhesivos_for_material llamado para material_id: {material_id}")
        if material_id is None:
            print("[CACHE CHECK] material_id es None, retornando lista vacía.")
            return []

        # La función interna _operation no se cacheará individualmente,
        # pero su resultado sí a través del decorador externo.
        def _operation():
            try:
                print(f"  [_operation] Intentando query para material_id: {material_id}")
                # Query material_adhesivo, join with adhesivos, filter by material_id
                response = (_self.supabase.table('material_adhesivo')
                    .select('adhesivos(*)') 
                    .eq('material_id', material_id)
                    .execute())
                
                # Log detallado de la respuesta cruda
                print(f"  [_operation] Respuesta DB cruda: {response}")
                if hasattr(response, 'data'):
                     print(f"  [_operation] Datos en respuesta DB: {response.data}")
                if hasattr(response, 'error'):
                     print(f"  [_operation] Error en respuesta DB: {response.error}")
                
                adhesivos_compatibles = []
                if response.data:
                    print(f"  [_operation] Procesando {len(response.data)} items de la respuesta...")
                    # The result is a list of dicts like: [{'adhesivos': {'id': 1, 'tipo': '...', ...}}, ...]
                    for item in response.data:
                        adhesivo_data = item.get('adhesivos')
                        print(f"    Item: {item}, Adhesivo Data Extraído: {adhesivo_data}") # Log cada item
                        if adhesivo_data:
                            try:
                                adhesivos_compatibles.append(Adhesivo(**adhesivo_data))
                            except TypeError as te:
                                print(f"    Error creando Adhesivo: {te}, Datos: {adhesivo_data}")
                        else:
                             print("    Item no contenía clave 'adhesivos' o era None.")
                else:
                     print("  [_operation] response.data estaba vacío o era None.")
                
                print(f"  [_operation] Final: {len(adhesivos_compatibles)} adhesivos compatibles encontrados.")
                return adhesivos_compatibles
            except Exception as e:
                print(f"  [_operation] EXCEPCIÓN en fetching: {e}")
                logging.error(f"Error fetching compatible adhesivos for material {material_id}: {e}", exc_info=True)
                return None # Return None to trigger retry

        # Llamada a _retry_operation (que llama a _operation)
        print(f"[CACHE CHECK] Llamando a _retry_operation para material_id: {material_id}")
        result = _self._retry_operation(f"fetching compatible adhesivos for material {material_id}", _operation)
        print(f"[CACHE CHECK] Resultado final para material_id {material_id} (después de retry): {'Lista vacía' if not result else f'{len(result)} items'}")
        return result if result is not None else []

    # --- FIN NUEVA FUNCIÓN ---
    
    # --- NUEVO MÉTODO ---
    def get_material_adhesivo_entry(self, material_id: int, adhesivo_id: int) -> Optional[Dict]:
        """
        Obtiene la fila completa de la tabla material_adhesivo para una combinación específica.

        Args:
            material_id: ID del material.
            adhesivo_id: ID del adhesivo.

        Returns:
            Un diccionario representando la fila encontrada (incluyendo su 'id') o None si no se encuentra o hay error.
        """
        def _operation():
            if material_id is None or adhesivo_id is None:
                print("Error: material_id y adhesivo_id son requeridos para get_material_adhesivo_entry")
                return None
            try:
                print(f"Querying material_adhesivo for entry: material_id={material_id}, adhesivo_id={adhesivo_id}")
                response = (self.supabase.table('material_adhesivo')
                    .select('*') # Seleccionar todas las columnas, incluyendo el 'id' de esta tabla
                    .eq('material_id', material_id)
                    .eq('adhesivo_id', adhesivo_id)
                    .limit(1)
                    .execute())

                if response.data:
                    entry = response.data[0]
                    print(f"Found material_adhesivo entry: {entry}")
                    return entry
                else:
                    print("No matching material_adhesivo entry found.")
                    return None # No combination found
            except Exception as e:
                print(f"Error fetching material_adhesivo entry: {e}")
                logging.error(f"Error fetching material_adhesivo entry for material={material_id}, adhesivo={adhesivo_id}: {e}", exc_info=True)
                return None # Return None on error to allow retry or indicate failure

        # Retry the operation
        result = self._retry_operation(f"fetching material_adhesivo entry ({material_id}/{adhesivo_id})", _operation)
        return result
    # --- FIN NUEVO MÉTODO ---

    #@st.cache_data
    def get_referencia_cliente_by_details(self, cliente_id: int, descripcion: str, comercial_id: str) -> Optional[ReferenciaCliente]:
        """Busca una referencia específica por cliente, descripción y comercial."""
        def _operation():
            try:
                print(f"Buscando referencia: cliente_id={cliente_id}, descripcion='{descripcion}', comercial_id={comercial_id}")
                response = self.supabase.from_('referencias_cliente') \
                    .select('*, cliente:clientes(*), perfil:perfiles(*)') \
                    .eq('cliente_id', cliente_id) \
                    .eq('descripcion', descripcion) \
                    .eq('id_usuario', comercial_id) \
                    .maybe_single() \
                    .execute()

                if response.data:
                    print(f"Referencia encontrada: {response.data['id']}")
                    # Reconstruir el objeto ReferenciaCliente
                    ref_data = response.data
                    cliente_data = ref_data.pop('cliente', None)
                    perfil_data = ref_data.pop('perfil', None)
                    
                    ref_obj = ReferenciaCliente(**ref_data)
                    if cliente_data:
                        ref_obj.cliente = Cliente(**cliente_data)
                    if perfil_data:
                        ref_obj.perfil = perfil_data # Asumiendo que perfil es un Dict
                        
                    return ref_obj
                else:
                    print("Referencia no encontrada con esos detalles.")
                    return None
            except Exception as e:
                print(f"Error buscando referencia por detalles: {e}")
                traceback.print_exc()
                return None # Indicar error

        try:
            # Nota: No usamos _retry_operation aquí porque un None es un resultado válido (no encontrado)
            # Si hay un error de conexión, Supabase debería lanzarlo y ser capturado por el llamador
            return _operation()
        except Exception as e:
            # Captura errores inesperados en _operation
            print(f"Excepción final buscando referencia por detalles: {e}")
            return None

    #@st.cache_data
    
    # --- MÉTODOS PARA GESTIÓN DE MATERIALES-ADHESIVOS Y ACABADOS ---
    def get_materiales_adhesivos_table(self) -> List[Dict]:
        """
        Obtiene todas las combinaciones de material-adhesivo con sus valores.
        
        Returns:
            Lista de diccionarios con la información completa de material-adhesivo.
        """
        try:
            # Consulta con join para obtener nombres de material y adhesivo
            response = (self.supabase.from_('material_adhesivo')
                .select('id, material_id, adhesivo_id, valor, code, materiales(nombre), adhesivos(tipo)')
                .execute())
                
            if not response.data:
                return []
                
            # Transformar los resultados para que sean más fáciles de usar
            result = []
            for item in response.data:
                # Crear un diccionario plano con toda la información
                entry = {
                    'id': item['id'],
                    'material_id': item['material_id'],
                    'adhesivo_id': item['adhesivo_id'],
                    'valor': item['valor'],
                    'code': item.get('code', ''),
                    'material_nombre': item['materiales']['nombre'] if item.get('materiales') else 'Desconocido',
                    'adhesivo_tipo': item['adhesivos']['tipo'] if item.get('adhesivos') else 'Desconocido'
                }
                result.append(entry)
                
            return result
                
        except Exception as e:
            print(f"Error obteniendo tabla material_adhesivo: {e}")
            logging.error(f"Error obteniendo tabla material_adhesivo: {e}", exc_info=True)
            return []
    
    def actualizar_material_adhesivo_valor(self, material_adhesivo_id: int, nuevo_valor: float) -> bool:
        """
        Actualiza el valor de una combinación material-adhesivo específica.
        
        Args:
            material_adhesivo_id: ID de la entrada en la tabla material_adhesivo.
            nuevo_valor: Nuevo valor (precio) a establecer.
            
        Returns:
            bool: True si la actualización fue exitosa, False en caso contrario.
        """
        try:
            # Validar el ID y el nuevo valor
            if material_adhesivo_id is None or material_adhesivo_id <= 0:
                print(f"ID de material_adhesivo inválido: {material_adhesivo_id}")
                return False
                
            if nuevo_valor is None or nuevo_valor < 0:
                print(f"Valor inválido para material_adhesivo: {nuevo_valor}")
                return False
            
            # El campo 'valor' en la base de datos es de tipo INTEGER, convertir a entero
            nuevo_valor_int = int(round(float(nuevo_valor)))
            
            # Actualizar el valor con el valor entero
            print(f"Actualizando material_adhesivo ID {material_adhesivo_id} con valor {nuevo_valor_int} (entero)")
            response = self.supabase.table('material_adhesivo').update(
                {"valor": nuevo_valor_int}
            ).eq('id', material_adhesivo_id).execute()
            
            # Verificar la respuesta
            if hasattr(response, 'error') and response.error:
                print(f"Error actualizando material_adhesivo: {response.error}")
                return False
            
            # Verificar que haya datos en la respuesta
            if not response.data:
                print("No se recibieron datos de respuesta en la actualización")
                # En este caso, aún podríamos considerar éxito dependiendo del API
                # Si el API retorna array vacío cuando no hay cambios
                
            print(f"Actualización exitosa para material_adhesivo ID {material_adhesivo_id}")
            print(f"Respuesta de API: {response.data}")
            return True
                
        except Exception as e:
            print(f"Error en actualizar_material_adhesivo_valor: {e}")
            logging.error(f"Error en actualizar_material_adhesivo_valor para ID {material_adhesivo_id}: {e}", exc_info=True)
            traceback.print_exc()  # Añadir stacktrace para mejor diagnóstico
            return False

    def actualizar_acabado_valor(self, acabado_id: int, nuevo_valor: float) -> bool:
        """
        Actualiza el valor de un acabado específico.
        
        Args:
            acabado_id: ID del acabado.
            nuevo_valor: Nuevo valor (precio) a establecer.
            
        Returns:
            bool: True si la actualización fue exitosa, False en caso contrario.
        """
        try:
            # Validar el ID y el nuevo valor
            if acabado_id is None or acabado_id <= 0:
                print(f"ID de acabado inválido: {acabado_id}")
                return False
                
            if nuevo_valor is None or nuevo_valor < 0:
                print(f"Valor inválido para acabado: {nuevo_valor}")
                return False
            
            # El campo 'valor' en la base de datos probablemente también es INTEGER
            nuevo_valor_int = int(round(float(nuevo_valor)))
            
            # Actualizar el valor con el valor entero
            print(f"Actualizando acabado ID {acabado_id} con valor {nuevo_valor_int} (entero)")
            response = self.supabase.table('acabados').update(
                {"valor": nuevo_valor_int}
            ).eq('id', acabado_id).execute()
            
            # Verificar la respuesta
            if hasattr(response, 'error') and response.error:
                print(f"Error actualizando acabado: {response.error}")
                return False
            
            # Verificar que haya datos en la respuesta
            if not response.data:
                print("No se recibieron datos de respuesta en la actualización")
                # En este caso, aún podríamos considerar éxito dependiendo del API
            
            print(f"Actualización exitosa para acabado ID {acabado_id}")
            print(f"Respuesta de API: {response.data}")
            return True
                
        except Exception as e:
            print(f"Error en actualizar_acabado_valor: {e}")
            logging.error(f"Error en actualizar_acabado_valor para ID {acabado_id}: {e}", exc_info=True)
            traceback.print_exc()  # Añadir stacktrace para mejor diagnóstico
            return False
    # --- FIN MÉTODOS PARA GESTIÓN DE MATERIALES-ADHESIVOS Y ACABADOS ---

    # --- NUEVO MÉTODO ---
    def get_material_adhesivo_entry(self, material_id: int, adhesivo_id: int) -> Optional[Dict]:
        """
        Obtiene la fila completa de la tabla material_adhesivo para una combinación específica.

        Args:
            material_id: ID del material.
            adhesivo_id: ID del adhesivo.

        Returns:
            Un diccionario representando la fila encontrada (incluyendo su 'id') o None si no se encuentra o hay error.
        """
        def _operation():
            if material_id is None or adhesivo_id is None:
                print("Error: material_id y adhesivo_id son requeridos para get_material_adhesivo_entry")
                return None
            try:
                print(f"Querying material_adhesivo for entry: material_id={material_id}, adhesivo_id={adhesivo_id}")
                response = (self.supabase.table('material_adhesivo')
                    .select('*') # Seleccionar todas las columnas, incluyendo el 'id' de esta tabla
                    .eq('material_id', material_id)
                    .eq('adhesivo_id', adhesivo_id)
                    .limit(1)
                    .execute())

                if response.data:
                    entry = response.data[0]
                    print(f"Found material_adhesivo entry: {entry}")
                    return entry
                else:
                    print("No matching material_adhesivo entry found.")
                    return None # No combination found
            except Exception as e:
                print(f"Error fetching material_adhesivo entry: {e}")
                logging.error(f"Error fetching material_adhesivo entry for material={material_id}, adhesivo={adhesivo_id}: {e}", exc_info=True)
                return None # Return None on error to allow retry or indicate failure

        # Retry the operation
        result = self._retry_operation(f"fetching material_adhesivo entry ({material_id}/{adhesivo_id})", _operation)
        return result
    # --- FIN NUEVO MÉTODO ---

    #@st.cache_data