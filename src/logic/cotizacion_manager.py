from typing import List, Dict, Optional, Tuple, Any
from decimal import Decimal
from datetime import datetime
import traceback
import streamlit as st # Necesario para acceder a session_state en algunos casos

# Importaciones relativas desde la misma capa o capas inferiores (data, config)
from ..data.database import DBManager
from ..data.models import Cotizacion, Escala, ReferenciaCliente, TipoGrafado

class CotizacionManagerError(Exception):
    """Custom exception for CotizacionManager errors."""
    pass

class CotizacionManager:
    """
    Gestiona la lógica de negocio para la creación y actualización de cotizaciones.
    Actúa como intermediario entre la UI y la capa de datos (DBManager).
    """

    def __init__(self, db: DBManager):
        if not isinstance(db, DBManager):
            raise TypeError("db must be an instance of DBManager")
        self.db = db

    def preparar_nueva_cotizacion_model(self, **kwargs) -> Cotizacion:
        """
        Prepara una nueva instancia de la dataclass Cotizacion (aún sin ID) 
        a partir de los datos del formulario y los resultados del cálculo.
        Realiza la transformación de los resultados de escala.
        
        kwargs esperados:
            - material_adhesivo_id: int # ID de la combinación material-adhesivo
            - acabado_id: int
            - num_tintas: int
            - num_paquetes_rollos: int
            - es_manga: bool
            - tipo_grafado: Optional[str] # Nombre del grafado
            - valor_troquel: float
            - valor_plancha_separado: Optional[float]
            - planchas_x_separado: bool
            - existe_troquel: bool
            - numero_pistas: int
            - avance: float
            - ancho: float
            - tipo_producto_id: int
            - forma_pago_id: int
            - altura_grafado: Optional[float]
            - escalas_resultados: List[Dict] # Resultado del cálculo
        """
        print("\n=== Preparando NUEVO modelo Cotizacion ===")
        try:
            cotizacion = Cotizacion()
            cotizacion.id = None  # Es nueva
            cotizacion.estado_id = 1  # Estado por defecto 'borrador' o 'pendiente'
            cotizacion.referencia_cliente_id = None # Se asignará al guardar
            cotizacion.numero_cotizacion = None # Se asignará al guardar

            # Asignar campos básicos desde kwargs, usando .get() con valores por defecto seguros
            # cotizacion.material_id = kwargs.get('material_id') # Ya no se usa material_id directamente
            cotizacion.material_adhesivo_id = kwargs.get('material_adhesivo_id') # Usar el ID de material_adhesivo
            cotizacion.acabado_id = kwargs.get('acabado_id')
            cotizacion.num_tintas = int(kwargs.get('num_tintas', 0))
            cotizacion.num_paquetes_rollos = int(kwargs.get('num_paquetes_rollos', 0))
            cotizacion.es_manga = bool(kwargs.get('es_manga', False))
            cotizacion.valor_troquel = Decimal(str(kwargs.get('valor_troquel', 0.0))) 
            cotizacion.valor_plancha_separado = Decimal(str(kwargs.get('valor_plancha_separado'))) if kwargs.get('valor_plancha_separado') is not None else None
            cotizacion.planchas_x_separado = bool(kwargs.get('planchas_x_separado', False))
            cotizacion.existe_troquel = bool(kwargs.get('existe_troquel', False))
            cotizacion.numero_pistas = int(kwargs.get('numero_pistas', 1))
            cotizacion.tipo_producto_id = kwargs.get('tipo_producto_id')
            cotizacion.ancho = float(kwargs.get('ancho', 0.0))
            cotizacion.avance = float(kwargs.get('avance', 0.0))
            cotizacion.forma_pago_id = kwargs.get('forma_pago_id', 1) # Default a 1 si no se provee
            cotizacion.altura_grafado = float(kwargs.get('altura_grafado')) if kwargs.get('altura_grafado') is not None else None
            cotizacion.fecha_creacion = datetime.now()
            cotizacion.ultima_modificacion_inputs = datetime.now() # Marcar como modificado
            cotizacion.identificador = None # Se generará al guardar
            cotizacion.modificado_por = st.session_state.get('user_id') # Asumiendo que user_id está en session_state

            # Procesar escalas
            escalas_resultados = kwargs.get('escalas_resultados', [])
            cotizacion.escalas = self._transformar_escalas(escalas_resultados)

            # Determinar tipo_grafado_id
            tipo_grafado_nombre = kwargs.get('tipo_grafado')
            if cotizacion.es_manga and tipo_grafado_nombre:
                try:
                    cotizacion.tipo_grafado_id = self.db.get_tipos_grafado_id_by_name(tipo_grafado_nombre)
                    print(f"ID de Grafado '{tipo_grafado_nombre}' obtenido: {cotizacion.tipo_grafado_id}")
                except Exception as e_graf:
                    print(f"Error obteniendo ID para grafado '{tipo_grafado_nombre}': {e_graf}")
                    # Considerar lanzar error o dejarlo None
                    cotizacion.tipo_grafado_id = None
            else:
                cotizacion.tipo_grafado_id = None

            print("Modelo Cotizacion NUEVO preparado:")
            # Imprimir algunos campos para verificar
            # print(f"  Material ID: {cotizacion.material_id}")
            print(f"  Material Adhesivo ID: {cotizacion.material_adhesivo_id}") # Imprimir el nuevo ID
            print(f"  Acabado ID: {cotizacion.acabado_id}")
            print(f"  Num Tintas: {cotizacion.num_tintas}")
            print(f"  Es Manga: {cotizacion.es_manga}")
            print(f"  Forma Pago ID: {cotizacion.forma_pago_id}")
            print(f"  Altura Grafado: {cotizacion.altura_grafado}")
            print(f"  Tipo Grafado ID: {cotizacion.tipo_grafado_id}")
            print(f"  Número de escalas procesadas: {len(cotizacion.escalas)}")

            return cotizacion

        except Exception as e:
            print(f"Error en preparar_nueva_cotizacion_model: {str(e)}")
            traceback.print_exc()
            # Re-lanzar como error específico del manager
            raise CotizacionManagerError(f"Error preparando nuevo modelo de cotización: {e}") from e

    def actualizar_cotizacion_model(self, cotizacion_existente: Cotizacion, **kwargs) -> Cotizacion:
        """
        Actualiza una instancia existente de la dataclass Cotizacion con nuevos datos
        del formulario y nuevos resultados de cálculo.
        Realiza la transformación de los nuevos resultados de escala.

        kwargs esperados: Mismos que preparar_nueva_cotizacion_model, ya que se 
                        pueden actualizar todos los campos editables.
        """
        print(f"\n=== Actualizando modelo Cotizacion ID: {cotizacion_existente.id} ===")
        if not isinstance(cotizacion_existente, Cotizacion) or cotizacion_existente.id is None:
             raise ValueError("Se requiere una instancia de Cotizacion válida con ID para actualizar.")
             
        cotizacion = cotizacion_existente # Trabajar sobre la instancia existente
        
        try:
            # Actualizar campos básicos desde kwargs si están presentes
            # Usar .get(key, cotizacion.existing_value) para mantener valor anterior si no se provee
            cotizacion.material_adhesivo_id = kwargs.get('material_adhesivo_id', cotizacion.material_adhesivo_id)
            cotizacion.acabado_id = kwargs.get('acabado_id', cotizacion.acabado_id)
            cotizacion.num_tintas = int(kwargs.get('num_tintas', cotizacion.num_tintas))
            cotizacion.num_paquetes_rollos = int(kwargs.get('num_paquetes_rollos', cotizacion.num_paquetes_rollos))
            cotizacion.es_manga = bool(kwargs.get('es_manga', cotizacion.es_manga))
            cotizacion.valor_troquel = Decimal(str(kwargs.get('valor_troquel', cotizacion.valor_troquel)))
            cotizacion.valor_plancha_separado = Decimal(str(kwargs.get('valor_plancha_separado'))) if kwargs.get('valor_plancha_separado') is not None else cotizacion.valor_plancha_separado
            cotizacion.planchas_x_separado = bool(kwargs.get('planchas_x_separado', cotizacion.planchas_x_separado))
            cotizacion.existe_troquel = bool(kwargs.get('existe_troquel', cotizacion.existe_troquel))
            cotizacion.numero_pistas = int(kwargs.get('numero_pistas', cotizacion.numero_pistas))
            cotizacion.tipo_producto_id = kwargs.get('tipo_producto_id', cotizacion.tipo_producto_id)
            cotizacion.ancho = float(kwargs.get('ancho', cotizacion.ancho))
            cotizacion.avance = float(kwargs.get('avance', cotizacion.avance))
            cotizacion.forma_pago_id = kwargs.get('forma_pago_id', cotizacion.forma_pago_id)
            cotizacion.altura_grafado = float(kwargs.get('altura_grafado')) if kwargs.get('altura_grafado') is not None else cotizacion.altura_grafado
            cotizacion.ultima_modificacion_inputs = datetime.now() # Siempre actualizar timestamp
            # cotizacion.modificado_por = st.session_state.get('user_id') # Actualizar quién modificó
            cotizacion.modificado_por = kwargs.get('modificado_por', st.session_state.get('user_id')) # Permitir pasar explícitamente

            # Campos que usualmente no se editan directamente aquí 
            # (como cliente_id, referencia_cliente_id, estado_id) se manejan al guardar si es necesario.

            # Procesar y *reemplazar* las escalas con los nuevos resultados
            nuevas_escalas_resultados = kwargs.get('escalas_resultados', [])
            cotizacion.escalas = self._transformar_escalas(nuevas_escalas_resultados)

            # Determinar *nuevo* tipo_grafado_id
            tipo_grafado_nombre = kwargs.get('tipo_grafado')
            if cotizacion.es_manga and tipo_grafado_nombre:
                try:
                    cotizacion.tipo_grafado_id = self.db.get_tipos_grafado_id_by_name(tipo_grafado_nombre)
                    print(f"ID de Grafado '{tipo_grafado_nombre}' actualizado: {cotizacion.tipo_grafado_id}")
                except Exception as e_graf:
                    print(f"Error obteniendo ID para grafado '{tipo_grafado_nombre}' en actualización: {e_graf}")
                    cotizacion.tipo_grafado_id = None
            elif not cotizacion.es_manga:
                cotizacion.tipo_grafado_id = None # Asegurar None si ya no es manga
            # Si es manga pero no se provee tipo_grafado, mantener el existente
            
            print("Modelo Cotizacion ACTUALIZADO:")
            # Imprimir algunos campos para verificar
            print(f"  ID: {cotizacion.id}")
            print(f"  Material Adhesivo ID: {cotizacion.material_adhesivo_id}")
            print(f"  Forma Pago ID: {cotizacion.forma_pago_id}")
            print(f"  Número de escalas actualizadas: {len(cotizacion.escalas)}")

            return cotizacion

        except Exception as e:
            print(f"Error en actualizar_cotizacion_model: {str(e)}")
            traceback.print_exc()
            # Re-lanzar como error específico del manager
            raise CotizacionManagerError(f"Error actualizando modelo de cotización existente: {e}") from e

    def guardar_nueva_cotizacion(
        self, 
        cotizacion_model: Cotizacion, 
        cliente_id: int, 
        referencia_descripcion: str, 
        comercial_id: str,
        datos_calculo: Dict[str, Any] # Diccionario con resultados del cálculo para tabla calculos_escala
    ) -> Tuple[bool, str, Optional[int]]:
        """
        Orquesta el guardado de una nueva cotización en la BD.
        1. Obtiene o crea la ReferenciaCliente.
        2. Asigna el ID de referencia al modelo.
        3. Llama a db.crear_cotizacion (pasando datos calculo también).
        4. Llama a db.guardar_cotizacion_escalas.
        Devuelve (éxito, mensaje, cotizacion_id).
        """
        print("\n=== Iniciando guardado de NUEVA cotización ===")
        cotizacion_id = None # Inicializar ID
        try:
            # 1. Obtener o crear la referencia
            referencia_id = self._obtener_o_crear_referencia(cliente_id, referencia_descripcion, comercial_id)
            if referencia_id is None:
                # El error ya se logueó en el helper, pero generamos mensaje para UI
                return False, "Error crítico: No se pudo obtener o crear la referencia de cliente necesaria.", None
                
            # 2. Asignar ID de referencia al modelo
            cotizacion_model.referencia_cliente_id = referencia_id
            print(f"Asignado referencia_cliente_id: {referencia_id}")
            
            # 3. Preparar datos y crear cotización principal
            # Convertir el modelo dataclass a un diccionario para la BD
            # Asegurarse de incluir el id_usuario (comercial_id) y referencia_cliente_id
            datos_bd = cotizacion_model.__dict__.copy() # Crear copia para no modificar el original
            datos_bd.pop('escalas', None) # Eliminar la lista de objetos escala
            datos_bd.pop('cliente', None) # Eliminar objetos relacionales si existen
            datos_bd.pop('referencia_cliente', None)
            datos_bd.pop('material', None)
            datos_bd.pop('acabado', None)
            datos_bd.pop('tipo_producto', None)
            datos_bd.pop('forma_pago', None)
            datos_bd.pop('perfil_comercial_info', None) # Eliminar este campo si existe
            datos_bd.pop('tipo_grafado', None) # Eliminar el nombre, ya tenemos el ID
            
            # CORRECCIÓN: Asegurar que se usa 'material_adhesivo_id' si existe en el modelo
            # y que se obtiene del modelo correcto
            if hasattr(cotizacion_model, 'material_adhesivo_id'):
                 # Asignar el valor de material_adhesivo_id del modelo a la clave correcta
                 datos_bd['material_adhesivo_id'] = cotizacion_model.material_adhesivo_id
                 # Eliminar la clave 'material_id' original si existe para evitar confusión
                 datos_bd.pop('material_id', None)
                 print(f"Se usará material_adhesivo_id: {datos_bd['material_adhesivo_id']}")
            else:
                 # Si el modelo por alguna razón no tiene material_adhesivo_id, 
                 # asegurar que la clave exista como None para la BD y eliminar material_id si existe.
                 print("Advertencia: El atributo 'material_adhesivo_id' no está en el cotizacion_model. Se enviará 'material_adhesivo_id' como None.")
                 datos_bd['material_adhesivo_id'] = None
                 datos_bd.pop('material_id', None) # Eliminar la clave antigua por si acaso

            # Asegurar tipos correctos para JSON (Decimal a float)
            if isinstance(datos_bd.get('valor_troquel'), Decimal):
                datos_bd['valor_troquel'] = float(datos_bd['valor_troquel'])
            if isinstance(datos_bd.get('valor_plancha_separado'), Decimal):
                datos_bd['valor_plancha_separado'] = float(datos_bd['valor_plancha_separado'])
                
            # Añadir id_usuario explícitamente (el comercial que crea)
            datos_bd['id_usuario'] = comercial_id
            
            print("\nDatos preparados para db.crear_cotizacion:")
            for k, v in datos_bd.items():
                print(f"  {k}: {v} ({type(v)})")
            
            # --- Añadir campos de cálculo para la función RPC --- 
            print("\nAñadiendo datos de cálculo para la función RPC...")
            campos_calculo_requeridos = [
                'valor_material', 'valor_plancha', 'valor_acabado', 'valor_troquel',
                'rentabilidad', 'avance', 'ancho', 'unidad_z_dientes',
                'existe_troquel', 'planchas_x_separado', 'num_tintas',
                'numero_pistas', 'num_paquetes_rollos', 'tipo_producto_id',
                'tipo_grafado_id'
            ]
            for campo in campos_calculo_requeridos:
                if campo in datos_calculo:
                    valor_calculo = datos_calculo[campo]
                    # Ajuste especial para valor_plancha
                    if campo == 'valor_plancha_para_calculo':
                        datos_bd['valor_plancha'] = float(valor_calculo) if valor_calculo is not None else 0.0
                        print(f"  Añadido 'valor_plancha': {datos_bd['valor_plancha']}")
                    else:
                        # Convertir a float si es numérico para asegurar compatibilidad JSON/RPC
                        if isinstance(valor_calculo, bool):
                            datos_bd[campo] = valor_calculo # Mantener bool
                        elif isinstance(valor_calculo, int):
                            datos_bd[campo] = valor_calculo # Mantener int
                        elif isinstance(valor_calculo, (float, Decimal)):
                            # Convertir float o Decimal a float para JSON/RPC
                            datos_bd[campo] = float(valor_calculo) if valor_calculo is not None else None
                        else:
                            # Mantener otros tipos (None, str, etc.)
                            datos_bd[campo] = valor_calculo
                        print(f"  Añadido '{campo}': {datos_bd.get(campo)} (Tipo: {type(datos_bd.get(campo))})") # Añadir tipo al log
                else:
                    print(f"  Advertencia: Campo de cálculo '{campo}' no encontrado en datos_calculo.")
            # --------------------------------------------------

            resultado_creacion = self.db.crear_cotizacion(datos_bd)
            
            if not resultado_creacion or 'id' not in resultado_creacion:
                error_msg = "Error al crear el registro principal de la cotización en la BD."
                print(error_msg)
                return False, error_msg, None
            
            cotizacion_id = resultado_creacion['id']
            cotizacion_model.id = cotizacion_id # Actualizar ID en el modelo
            print(f"Cotización principal creada con ID: {cotizacion_id}")
            
            # 4. Guardar las escalas
            if cotizacion_model.escalas:
                print(f"\nGuardando {len(cotizacion_model.escalas)} escalas...")
                success_escalas = self.db.guardar_cotizacion_escalas(cotizacion_id, cotizacion_model.escalas)
                if not success_escalas:
                    # La cotización se creó, pero las escalas fallaron. Advertencia.
                    warning_msg = f"Cotización creada (ID: {cotizacion_id}), pero falló el guardado de las escalas."
                    print(warning_msg)
                    # Devolver éxito parcial con advertencia
                    return True, warning_msg, cotizacion_id 
            else:
                print("No hay escalas para guardar.")
            
            # Todo OK
            success_msg = f"Cotización creada exitosamente con ID: {cotizacion_id}"
            print(f"\n=== Fin guardado NUEVA cotización ===")
            return True, success_msg, cotizacion_id

        except CotizacionManagerError as cme: # Capturar errores específicos del manager
            print(f"Error de lógica de negocio: {cme}")
            return False, str(cme), None
        except Exception as e:
            print(f"Error inesperado en guardar_nueva_cotizacion: {e}")
            traceback.print_exc()
            return False, f"Error inesperado al guardar la cotización: {e}", None

    def actualizar_cotizacion_existente(
        self, 
        cotizacion_id: int, 
        cotizacion_model: Cotizacion, 
        cliente_id: int, # Aunque no cambia, puede ser útil para validación
        referencia_descripcion: str, 
        comercial_id: str, # Quién puede modificar o a quién se reasigna
        datos_calculo: Dict[str, Any], # Nuevos datos de cálculo
        modificado_por: str # ID del usuario que realiza la modificación
    ) -> Tuple[bool, str]:
        """
        Orquesta la actualización de una cotización existente en la BD.
        1. Obtiene la ReferenciaCliente existente (NO crea una nueva).
        2. Actualiza la descripción de la ReferenciaCliente si ha cambiado.
        3. Actualiza los datos principales de la cotización (usando db.actualizar_cotizacion).
        4. Elimina los cálculos de escala anteriores (db.eliminar_calculos_escala).
        5. Guarda los nuevos cálculos de escala (db.guardar_calculos_escala).
        6. Elimina los resultados de escala anteriores (db.eliminar_cotizacion_escalas).
        7. Guarda los nuevos resultados de escala (db.guardar_cotizacion_escalas).
        Devuelve (éxito, mensaje).
        """
        print(f"\n=== Iniciando actualización de Cotización ID: {cotizacion_id} ===")
        try:
            # 0. Validar ID
            if cotizacion_id is None:
                return False, "ID de cotización inválido para actualizar."
            
            # 1. Obtener la referencia existente (asumiendo que ya existe y está vinculada)
            # Necesitamos obtener la referencia_cliente_id desde la cotización original
            cotizacion_original = self.db.obtener_cotizacion(cotizacion_id) # Necesitamos esta función
            if not cotizacion_original:
                return False, f"No se encontró la cotización original con ID {cotizacion_id}."
            
            referencia_id = cotizacion_original.referencia_cliente_id
            if referencia_id is None:
                 return False, "Error crítico: La cotización original no tiene una referencia asociada."
                 
            # 2. Actualizar descripción de la referencia si cambió
            referencia_original = self.db.get_referencia_cliente(referencia_id)
            if not referencia_original:
                 return False, f"Error crítico: No se encontró la referencia original con ID {referencia_id}."
            
            if referencia_original.descripcion != referencia_descripcion:
                print(f"Actualizando descripción de Referencia ID {referencia_id}...")
                # Asumiendo una función db.update_referencia_cliente(referencia_id, {'descripcion': ...})
                update_ref_success = self.db.update_referencia_cliente(referencia_id, {'descripcion': referencia_descripcion})
                if not update_ref_success:
                    return False, f"Error al actualizar la descripción de la referencia ID {referencia_id}."
            
            # 3. Preparar datos y actualizar cotización principal
            datos_bd = cotizacion_model.__dict__.copy()
            datos_bd.pop('id', None) # No se actualiza el ID
            datos_bd.pop('escalas', None) # Escalas se manejan por separado
            datos_bd.pop('fecha_creacion', None) # No se actualiza
            datos_bd.pop('numero_cotizacion', None) # No se actualiza
            datos_bd.pop('identificador', None) # Se podría recalcular y actualizar si es necesario
            datos_bd.pop('referencia_cliente_id', None) # No se cambia la referencia
            # Eliminar objetos relacionales
            datos_bd.pop('cliente', None)
            datos_bd.pop('referencia_cliente', None)
            datos_bd.pop('material', None)
            datos_bd.pop('acabado', None)
            datos_bd.pop('tipo_producto', None)
            datos_bd.pop('forma_pago', None)
            datos_bd.pop('perfil_comercial_info', None)
            datos_bd.pop('tipo_grafado', None)
            
            # Añadir quién modificó y asegurar comercial_id
            datos_bd['modificado_por'] = modificado_por
            datos_bd['comercial_id'] = comercial_id # Permitir reasignación por admin
            
            # Convertir Decimal a float
            for key in ['valor_troquel', 'valor_plancha_separado']:
                 if key in datos_bd and isinstance(datos_bd[key], Decimal):
                     datos_bd[key] = float(datos_bd[key])
                     
            # Asegurar que los campos None se manejen correctamente
            if 'valor_plancha_separado' in datos_bd and datos_bd['valor_plancha_separado'] is None:
                 # Si es None, asegurarse de que se envíe NULL a la BD si la función de update lo maneja
                 pass # O eliminar la clave si la función de update no actualiza si la clave no está
            if 'altura_grafado' in datos_bd and datos_bd['altura_grafado'] is None:
                 pass
                 
            print(f"Actualizando datos principales de Cotización ID {cotizacion_id}...")
            # Asumiendo una función db.update_cotizacion(cotizacion_id, datos_bd)
            update_coti_success, update_coti_msg = self.db.actualizar_cotizacion(cotizacion_id, datos_bd)
            if not update_coti_success:
                 return False, f"Error al actualizar la cotización principal: {update_coti_msg}"
                 
            # --- Actualizar Cálculos y Escalas --- 
            # Es más simple eliminar y volver a insertar que intentar actualizar en su lugar.
            
            # 4. Eliminar cálculos de escala anteriores
            print(f"Eliminando cálculos de escala anteriores para Cotización ID {cotizacion_id}...")
            delete_calc_success = self.db.eliminar_calculos_escala(cotizacion_id) # Necesita implementar esta función
            if not delete_calc_success:
                 # Podría ser un warning en lugar de error fatal si la tabla no existía o estaba vacía
                 print(f"Advertencia: No se pudieron eliminar los cálculos de escala anteriores para {cotizacion_id}.")
                 
            # 5. Guardar nuevos cálculos de escala
            print(f"Guardando nuevos cálculos de escala para Cotización ID {cotizacion_id}...")
            # Reutilizar la lógica de guardar_calculos_escala existente
            save_calc_success = self.db.guardar_calculos_escala(
                cotizacion_id=cotizacion_id,
                **datos_calculo # Desempaquetar el diccionario con los datos del cálculo
            )
            if not save_calc_success:
                return False, "Error al guardar los nuevos datos de cálculo."
                
            # 6. Eliminar resultados de escala anteriores
            print(f"Eliminando resultados de escala anteriores para Cotización ID {cotizacion_id}...")
            delete_esc_success = self.db.eliminar_cotizacion_escalas(cotizacion_id) # Necesita implementar esta función
            if not delete_esc_success:
                 print(f"Advertencia: No se pudieron eliminar los resultados de escala anteriores para {cotizacion_id}.")
                 
            # 7. Guardar nuevos resultados de escala
            print(f"Guardando nuevos resultados de escala para Cotización ID {cotizacion_id}...")
            # Reutilizar la lógica de guardar_cotizacion_escalas existente
            if cotizacion_model.escalas:
                 save_esc_success = self.db.guardar_cotizacion_escalas(cotizacion_id, cotizacion_model.escalas)
                 if not save_esc_success:
                     return False, "Error al guardar los nuevos resultados de escala."
            else:
                 print("No hay nuevas escalas para guardar.")

            # --- ACTUALIZAR calculos_escala ---
            print(f"Actualizando datos de cálculo (calculos_escala) para cotización ID: {cotizacion_id}")
            # 7. Eliminar datos de cálculo antiguos
            success_del_calc = self.db.eliminar_calculos_escala(cotizacion_id)
            if not success_del_calc:
                # Considerar si es error fatal o warning
                print(f"ADVERTENCIA: No se pudieron eliminar los datos de cálculo antiguos para {cotizacion_id}")
                # return False, "Error al eliminar datos de cálculo antiguos."

            # 8. Guardar nuevos datos de cálculo
            if datos_calculo: # Asegurarse que hay datos para guardar
                # La función guardar_calculos_escala espera argumentos nombrados, no un dict.
                # Desempacar el diccionario datos_calculo en argumentos nombrados.
                try:
                    print(f"Guardando nuevos datos de cálculo: {datos_calculo}")
                    success_calc = self.db.guardar_calculos_escala(cotizacion_id=cotizacion_id, **datos_calculo)
                    if not success_calc:
                         return False, f"Error al guardar nuevos datos de cálculo"
                except TypeError as te:
                    print(f"Error de TypeError al llamar a guardar_calculos_escala: {te}")
                    print("Verifique que las claves en 'datos_calculo' coincidan con los parámetros de la función.")
                    return False, "Error interno al intentar guardar datos de cálculo (parámetros no coinciden)."
            else:
                print("ADVERTENCIA: No se proporcionaron 'datos_calculo' para actualizar.")
            # -------------------------------------

            print(f"Actualización completada para cotización ID: {cotizacion_id}")
            return True, "✅ Cotización actualizada exitosamente"

        except Exception as e:
            print(f"Error en actualizar_cotizacion_existente: {e}")
            traceback.print_exc()
            return False, f"Error inesperado al actualizar la cotización: {e}"

    # --- Métodos Helper (si son necesarios) ---
    def _transformar_escalas(self, escalas_resultados: List[Dict]) -> List[Escala]:
        """
        Transforma la lista de diccionarios de resultados de cálculo
        en una lista de objetos Escala (dataclass).
        """
        escalas_transformadas = []
        if not escalas_resultados:
            return escalas_transformadas

        print(f"\nTransformando {len(escalas_resultados)} escalas...")
        for i, resultado in enumerate(escalas_resultados):
            try:
                # Asegurar que los campos necesarios existen y tienen valores válidos
                escala_val = int(resultado.get('escala', 0))
                valor_unidad_val = float(resultado.get('valor_unidad', 0.0))
                metros_val = float(resultado.get('metros', 0.0))
                tiempo_horas_val = float(resultado.get('tiempo_horas', 0.0))
                montaje_val = float(resultado.get('montaje', 0.0))
                mo_y_maq_val = float(resultado.get('mo_y_maq', 0.0))
                tintas_val = float(resultado.get('tintas', 0.0))
                papel_lam_val = float(resultado.get('papel_lam', 0.0))
                # Usar 'desperdicio' o 'desperdicio_total' si existe en el dict, sino 0.0
                desperdicio_total_val = float(resultado.get('desperdicio', resultado.get('desperdicio_total', 0.0)))

                escala_obj = Escala(
                    escala=escala_val,
                    valor_unidad=valor_unidad_val,
                    metros=metros_val,
                    tiempo_horas=tiempo_horas_val,
                    montaje=montaje_val,
                    mo_y_maq=mo_y_maq_val,
                    tintas=tintas_val,
                    papel_lam=papel_lam_val,
                    desperdicio_total=desperdicio_total_val
                )
                print(f"  Escala {i+1} transformada: {escala_obj.escala}, Valor: {escala_obj.valor_unidad:.2f}")
                escalas_transformadas.append(escala_obj)
            except (ValueError, TypeError, KeyError) as e:
                print(f"Error transformando escala {i+1} (Datos: {resultado}): {e}")
                # Opcional: lanzar una excepción o continuar con las siguientes escalas
                # raise CotizacionManagerError(f"Error en datos de escala: {e}") from e
                continue # Continuar con la siguiente escala
        
        print(f"Total de escalas transformadas: {len(escalas_transformadas)}")
        return escalas_transformadas
        
    def _obtener_o_crear_referencia(self, cliente_id: int, descripcion: str, comercial_id: str) -> Optional[int]:
        """
        Busca una referencia por cliente, descripción y comercial.
        Si no existe, la crea.
        Devuelve el ID de la referencia encontrada o creada, o None si hay error.
        """
        if not cliente_id or not descripcion or not comercial_id:
            print("Error: cliente_id, descripción y comercial_id son requeridos para obtener/crear referencia")
            return None
            
        try:
            print(f"Buscando/Creando referencia para Cliente {cliente_id}, Desc: '{descripcion}', Comercial: {comercial_id}")
            referencia_existente = self.db.get_referencia_cliente_by_details(cliente_id, descripcion, comercial_id)
            
            if referencia_existente:
                print(f"Referencia existente encontrada con ID: {referencia_existente.id}")
                return referencia_existente.id
            else:
                print("Referencia no encontrada, creando nueva...")
                nueva_referencia = ReferenciaCliente(
                    cliente_id=cliente_id,
                    descripcion=descripcion,
                    id_usuario=comercial_id # Asegurar que este campo se llame así en el modelo
                )
                referencia_guardada = self.db.crear_referencia(nueva_referencia)
                if referencia_guardada and referencia_guardada.id:
                    print(f"Nueva referencia creada con ID: {referencia_guardada.id}")
                    return referencia_guardada.id
                else:
                    print("Error: No se pudo crear la nueva referencia en la BD.")
                    # Aquí podríamos querer lanzar una excepción para detener el flujo
                    raise CotizacionManagerError("Fallo al crear la nueva referencia de cliente requerida.")

        except Exception as e:
            print(f"Error en _obtener_o_crear_referencia: {e}")
            traceback.print_exc()
            # Lanzar excepción para indicar fallo crítico
            raise CotizacionManagerError(f"Error obteniendo o creando referencia: {e}") from e

    def guardar_cotizacion(self, datos_calculados: dict) -> Tuple[bool, str]:
        """
        Guarda la cotización y, si es necesario, la nueva referencia
        """
        try:
            # Verificar si es referencia nueva o existente
            if 'nueva_referencia_temp' in st.session_state:
                # Crear referencia y cotización en una transacción
                datos_referencia = st.session_state.nueva_referencia_temp
                resultado = self.db.crear_referencia_y_cotizacion(
                    datos_referencia=datos_referencia,
                    datos_cotizacion=datos_calculados
                )
                
                if not resultado:
                    return False, "Error al crear la referencia y la cotización"
                
                # Limpiar la referencia temporal
                del st.session_state.nueva_referencia_temp
                
                return True, "Cotización y nueva referencia guardadas exitosamente"
            else:
                # Solo guardar la cotización
                response = self.db.guardar_cotizacion(datos_calculados)
                if not response:
                    return False, "Error al guardar la cotización"
                return True, "Cotización guardada exitosamente"
                
        except Exception as e:
            return False, f"Error al guardar: {str(e)}"