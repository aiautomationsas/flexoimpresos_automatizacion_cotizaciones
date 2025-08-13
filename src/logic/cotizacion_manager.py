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
            cotizacion.tipo_foil_id = kwargs.get('tipo_foil_id')  # Agregado campo tipo_foil_id
            cotizacion.num_tintas = int(kwargs.get('num_tintas', 0))
            cotizacion.num_paquetes_rollos = int(kwargs.get('num_paquetes_rollos', 0))
            cotizacion.es_manga = bool(kwargs.get('es_manga', False))
            # Manejar None o cadenas vacías para evitar ConversionSyntax
            _val_troquel = kwargs.get('valor_troquel', None)
            if _val_troquel is None or (isinstance(_val_troquel, str) and _val_troquel.strip() == ""):
                cotizacion.valor_troquel = None
            else:
                cotizacion.valor_troquel = Decimal(str(_val_troquel)) 
            cotizacion.valor_plancha_separado = Decimal(str(kwargs.get('valor_plancha_separado'))) if kwargs.get('valor_plancha_separado') is not None else None
            cotizacion.planchas_x_separado = bool(kwargs.get('planchas_x_separado', False))
            cotizacion.existe_troquel = bool(kwargs.get('existe_troquel', False))
            cotizacion.numero_pistas = int(kwargs.get('numero_pistas', 1))
            cotizacion.tipo_producto_id = kwargs.get('tipo_producto_id')
            cotizacion.ancho = float(kwargs.get('ancho', 0.0))
            cotizacion.avance = float(kwargs.get('avance', 0.0))

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
            # Actualizar campos básicos desde kwargs, manteniendo valores existentes como default
            cotizacion.material_adhesivo_id = kwargs.get('material_adhesivo_id', cotizacion.material_adhesivo_id)
            cotizacion.acabado_id = kwargs.get('acabado_id', cotizacion.acabado_id)
            cotizacion.tipo_foil_id = kwargs.get('tipo_foil_id', cotizacion.tipo_foil_id)  # Agregado campo tipo_foil_id
            cotizacion.num_tintas = int(kwargs.get('num_tintas', cotizacion.num_tintas))
            cotizacion.num_paquetes_rollos = int(kwargs.get('num_paquetes_rollos', cotizacion.num_paquetes_rollos))
            cotizacion.es_manga = bool(kwargs.get('es_manga', cotizacion.es_manga))
            _val_troquel_upd = kwargs.get('valor_troquel', cotizacion.valor_troquel)
            if _val_troquel_upd is None or (isinstance(_val_troquel_upd, str) and str(_val_troquel_upd).strip() == ""):
                cotizacion.valor_troquel = None
            else:
                cotizacion.valor_troquel = Decimal(str(_val_troquel_upd))
            cotizacion.valor_plancha_separado = Decimal(str(kwargs.get('valor_plancha_separado', cotizacion.valor_plancha_separado))) if kwargs.get('valor_plancha_separado') is not None else cotizacion.valor_plancha_separado
            cotizacion.planchas_x_separado = bool(kwargs.get('planchas_x_separado', cotizacion.planchas_x_separado))
            cotizacion.existe_troquel = bool(kwargs.get('existe_troquel', cotizacion.existe_troquel))
            cotizacion.numero_pistas = int(kwargs.get('numero_pistas', cotizacion.numero_pistas))
            cotizacion.tipo_producto_id = kwargs.get('tipo_producto_id', cotizacion.tipo_producto_id)
            cotizacion.ancho = float(kwargs.get('ancho', cotizacion.ancho))
            cotizacion.avance = float(kwargs.get('avance', cotizacion.avance))

            cotizacion.altura_grafado = float(kwargs.get('altura_grafado', cotizacion.altura_grafado)) if kwargs.get('altura_grafado') is not None else cotizacion.altura_grafado
            cotizacion.ultima_modificacion_inputs = datetime.now()
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
        datos_calculo: Dict[str, Any], # Diccionario con resultados del cálculo
        admin_ajustes_calculo: bool # <-- NUEVO PARÁMETRO
    ) -> Tuple[bool, str, Optional[int]]:
        """
        Orquesta el guardado de una nueva cotización en la BD.
        1. Obtiene o crea la ReferenciaCliente.
        2. Asigna el ID de referencia al modelo.
        3. Llama a db.crear_cotizacion (pasando datos calculo también).
        4. Llama a db.guardar_cotizacion_escalas.
        Devuelve (éxito, mensaje, cotizacion_id).
        Ahora incluye un flag para saber si admin aplicó ajustes durante el cálculo.
        """
        print("\n=== Iniciando guardado de NUEVA cotización ===")
        # *** DEBUG: Imprimir valores clave del modelo recibido ***
        print(f"---> DEBUG MANAGER: Modelo Recibido - Acabado ID: {cotizacion_model.acabado_id}, Foil ID: {cotizacion_model.tipo_foil_id}")
        # *** FIN DEBUG ***
        cotizacion_id = None # Inicializar ID
        try:
            # *** INICIO VALIDACIÓN ACABADO/FOIL ***
            acabado_id_check = cotizacion_model.acabado_id
            tipo_foil_id_check = cotizacion_model.tipo_foil_id # Ya debería ser int o None por preparar_nueva/actualizar

            print(f"Validando combinación Acabado ID: {acabado_id_check}, Foil ID: {tipo_foil_id_check}")

            if acabado_id_check in (5, 6): # Acabados que requieren foil
                if tipo_foil_id_check is None or tipo_foil_id_check <= 0: # Asumiendo que los IDs de foil son > 0
                    error_msg = f"❌ Se requiere un Tipo de Foil válido cuando el acabado es {acabado_id_check}."
                    print(error_msg)
                    return False, error_msg, None # Devolver False, mensaje de error, y None para cotizacion_id
            elif tipo_foil_id_check is not None: # Acabados que NO deben tener foil
                 error_msg = f"❌ No se debe seleccionar un Tipo de Foil cuando el acabado es {acabado_id_check}."
                 print(error_msg)
                 # También limpiar el ID en el modelo por si acaso antes de continuar (opcional, mejor fallar)
                 # cotizacion_model.tipo_foil_id = None
                 return False, error_msg, None # Devolver False, mensaje de error, y None para cotizacion_id
            
            print("Combinación Acabado/Foil válida.")
            # *** FIN VALIDACIÓN ACABADO/FOIL ***

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
    
            datos_bd.pop('perfil_comercial_info', None) # Eliminar este campo si existe
            datos_bd.pop('tipo_grafado', None) # Eliminar el nombre, ya tenemos el ID
            
            # Asegurar que tipo_foil_id sea entero o None
            if 'tipo_foil_id' in datos_bd:
                if datos_bd['tipo_foil_id'] == '' or datos_bd['tipo_foil_id'] is None:
                    datos_bd['tipo_foil_id'] = None
                else:
                    try:
                        datos_bd['tipo_foil_id'] = int(datos_bd['tipo_foil_id'])
                    except ValueError:
                        print(f"Advertencia: No se pudo convertir tipo_foil_id '{datos_bd['tipo_foil_id']}' a entero. Se establecerá a None.")
                        datos_bd['tipo_foil_id'] = None
            
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
            
            # --- NUEVO: Establecer el flag basado en el parámetro --- 
            datos_bd['ajustes_modificados_admin'] = admin_ajustes_calculo 
            print(f"---> Valor para 'ajustes_modificados_admin' (creación): {admin_ajustes_calculo}")
            # -------------------------------------------------------
            
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
            
            # Intentar guardar parametros_especiales si vienen en datos_calculo
            try:
                params_esp = datos_calculo.get('parametros_especiales') if isinstance(datos_calculo, dict) else None
                if params_esp:
                    _ = self.db.guardar_parametros_especiales(cotizacion_id, params_esp)
            except Exception as _:
                # No bloquear el flujo si falla
                pass
            
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
        modificado_por: str, # ID del usuario que realiza la modificación
        es_recotizacion: bool = None,
        admin_ajustes_activos: bool = False  # Nuevo parámetro para indicar si hay ajustes de admin activos
    ) -> Tuple[bool, str]:
        """
        Orquesta la actualización de una cotización existente en la BD.
        1. Obtiene o crea la ReferenciaCliente (si cambia la descripción).
        2. Asigna el ID de referencia actualizado al modelo.
        3. Determina si el flag 'ajustes_modificados_admin' debe ser True.
        4. Llama a db.actualizar_cotizacion (RPC) pasando los datos.
        Devuelve (éxito, mensaje).
        """
        print(f"\n=== Iniciando actualización de cotización ID: {cotizacion_id} ===")
        
        try:
            # --- PASO 1: VERIFICAR/ACTUALIZAR REFERENCIA CLIENTE ---
            print("\nVerificando referencia cliente...")
            # Obtener cotización actual para verificar si cambió la referencia
            cotizacion_actual = self.db.obtener_cotizacion(cotizacion_id)
            if not cotizacion_actual:
                error_msg = f"❌ No se pudo obtener la cotización actual con ID {cotizacion_id}."
                print(error_msg)
                return False, error_msg
                
            # Datos para el identificador (leerlos temprano para estar seguros)
            tipo_producto_nombre_actual = "MANGA" if cotizacion_model.es_manga else "ETIQUETA"
            cliente_obj = self.db.get_cliente(cliente_id)
            cliente_nombre_identificador = cliente_obj.nombre if cliente_obj else "CLIENTE"
            # Descripción referencia para identificador (puede ser la nueva o la existente)
            referencia_desc_identificador = referencia_descripcion
            # Necesitamos el número original para el identificador (no cambia)
            numero_cotizacion_original = cotizacion_actual.numero_cotizacion
            
            # Obtener la referencia actual
            referencia_actual = cotizacion_actual.referencia_cliente
            if not referencia_actual:
                error_msg = f"❌ No se pudo obtener la referencia actual para cotización {cotizacion_id}."
                print(error_msg)
                return False, error_msg
                
            referencia_id_actual = referencia_actual.id
            referencia_desc_actual = referencia_actual.descripcion
            propietario_actual_id = referencia_actual.id_usuario
            
            # Verificar si cambió la descripción de la referencia
            referencia_id_final = referencia_id_actual
            if referencia_descripcion != referencia_desc_actual:
                print(f"Descripción de referencia cambiada: '{referencia_desc_actual}' -> '{referencia_descripcion}'")
                
                # Verificar si ya existe una referencia con el nuevo nombre
                ref_existente = self.db.get_referencia_cliente_by_details(
                    cliente_id=cliente_id,
                    descripcion=referencia_descripcion,
                    comercial_id=comercial_id
                )
                
                if ref_existente:
                    # Usar la referencia existente
                    print(f"Se encontró referencia existente con ID {ref_existente.id}")
                    referencia_id_final = ref_existente.id
                else:
                    # Crear nueva referencia para este cliente con la nueva descripción
                    nueva_ref = ReferenciaCliente(
                        cliente_id=cliente_id,
                        descripcion=referencia_descripcion,
                        id_usuario=comercial_id
                    )
                    ref_creada = self.db.crear_referencia(nueva_ref)
                    if not ref_creada:
                        error_msg = f"❌ No se pudo crear la nueva referencia."
                        print(error_msg)
                        return False, error_msg
                        
                    referencia_id_final = ref_creada.id
                    print(f"Nueva referencia creada con ID {referencia_id_final}")
            else:
                print("Descripción de referencia sin cambios.")
                
            # Actualizar la referencia en el modelo
            cotizacion_model.referencia_cliente_id = referencia_id_final
            print(f"Referencia a usar para la actualización: {referencia_id_final}")
            # ------------------------------------------------------------------------

            # --- PASO 2: Lógica UNIFICADA para marcar 'ajustes_modificados_admin' --- 
            ajustes_modificados_por_admin_ahora = False
            
            # Verificar primero si el modificador es admin
            perfil_modificador = self.db.get_perfil(modificado_por)
            rol_modificador = perfil_modificador.get('rol_nombre') if perfil_modificador else None
            es_admin = (rol_modificador == 'administrador')
            
            # Verificar si hay cambios en valores relacionados con ajustes avanzados
            hay_cambios_ajustes_avanzados = False
            
            # Obtener los cálculos actuales para comparar
            calculos_actuales = self.db.get_calculos_escala_cotizacion(cotizacion_id)
            
            if calculos_actuales and datos_calculo:
                # Lista de campos de ajustes avanzados a verificar
                campos_ajustes = [
                    'rentabilidad',
                    'valor_material',
                    'valor_plancha_para_calculo',  # Clave en datos_calculo
                    'valor_troquel_total',         # Clave en datos_calculo
                    'valor_acabado'
                ]
                
                # Mapeo entre claves en datos_calculo y calculos_actuales
                mapeo_claves = {
                    'valor_plancha_para_calculo': 'valor_plancha',
                    'valor_troquel_total': 'valor_troquel'
                }
                
                # Verificar cada campo
                for campo in campos_ajustes:
                    if campo in datos_calculo:
                        # Obtener la clave correspondiente en calculos_actuales
                        clave_bd = mapeo_claves.get(campo, campo)
                        
                        if clave_bd in calculos_actuales:
                            valor_actual = float(calculos_actuales.get(clave_bd, 0.0))
                            valor_nuevo = float(datos_calculo.get(campo, 0.0))
                            
                            # Si hay diferencia significativa entre los valores
                            if abs(valor_actual - valor_nuevo) > 0.001:
                                hay_cambios_ajustes_avanzados = True
                                print(f"⚠️ Detectado cambio en {campo}: {valor_actual} -> {valor_nuevo}")
            
            # Determinar si se deben activar los ajustes de admin
            if admin_ajustes_activos:
                # Si el parámetro explícito está activo, usar ese valor directamente
                ajustes_modificados_por_admin_ahora = True
                print(f"⚠️ Detectados ajustes de admin activos a través del parámetro admin_ajustes_activos=True")
            elif es_admin and hay_cambios_ajustes_avanzados:
                # Si un admin está modificando ajustes avanzados, activar el flag
                ajustes_modificados_por_admin_ahora = True
                print(f"⚠️ Detectados ajustes de admin implícitos: Admin modificando valores avanzados.")
            elif es_admin:
                print(f"Admin está modificando pero sin cambios en ajustes avanzados.")
            
            # Obtener el valor actual del flag en la BD para preservarlo si ya está en TRUE
            valor_actual_flag_bd = False 
            try:
                response_flag = self.db.supabase.table('cotizaciones').select('ajustes_modificados_admin').eq('id', cotizacion_id).maybe_single().execute()
                if response_flag.data: valor_actual_flag_bd = response_flag.data.get('ajustes_modificados_admin', False)
                print(f"Valor actual del flag en BD: {valor_actual_flag_bd}")
            except Exception as e_flag: print(f"ERROR al leer flag: {e_flag}")
            
            # El flag final es TRUE si ya estaba en TRUE o si un admin lo está modificando ahora con ajustes activos
            flag_final_ajustes_admin = valor_actual_flag_bd or ajustes_modificados_por_admin_ahora
            print(f"Valor final del flag ajustes_modificados_admin a enviar: {flag_final_ajustes_admin}")
            # ------------------------------------------------------------------------

            # --- PASO 3: GENERAR Y VALIDAR IDENTIFICADOR --- 
            print("\nGenerando y validando identificador actualizado...")
            identificador_nuevo = ""
            try:
                mat_ad_id_actual = cotizacion_model.material_adhesivo_id
                material_code = self.db.get_material_adhesivo_code(mat_ad_id_actual) if mat_ad_id_actual else ""
                acabado_id_actual = cotizacion_model.acabado_id
                acabado_code = self.db.get_acabado_code(acabado_id_actual) if acabado_id_actual else ""
                # Preferir valores calculados si están disponibles para evitar redondeos en el identificador
                ancho_actual = datos_calculo.get('ancho_calculado', cotizacion_model.ancho) if 'datos_calculo' in locals() else cotizacion_model.ancho
                avance_actual = datos_calculo.get('avance_calculado', cotizacion_model.avance) if 'datos_calculo' in locals() else cotizacion_model.avance
                num_pistas_actual = cotizacion_model.numero_pistas
                num_tintas_actual = cotizacion_model.num_tintas
                num_paq_rollos_actual = cotizacion_model.num_paquetes_rollos
                
                identificador_nuevo = self.db._generar_identificador(
                    tipo_producto=tipo_producto_nombre_actual,
                    material_code=material_code,
                    ancho=ancho_actual,
                    avance=avance_actual,
                    num_pistas=num_pistas_actual,
                    num_tintas=num_tintas_actual,
                    acabado_code=acabado_code,
                    num_paquetes_rollos=num_paq_rollos_actual,
                    cliente=cliente_nombre_identificador, 
                    referencia=referencia_desc_identificador,
                    numero_cotizacion=numero_cotizacion_original
                )
                print(f"Nuevo identificador generado: {identificador_nuevo}")
                if self.db.check_identificador_exists(identificador_nuevo, cotizacion_id):
                    error_msg = f"❌ El identificador generado '{identificador_nuevo}' ya existe para otra cotización. No se puede actualizar."
                    print(error_msg)
                    return False, error_msg
                else:
                    print("Identificador nuevo es único.")
            except Exception as e_ident:
                print(f"Error generando o validando identificador: {e_ident}")
                traceback.print_exc()
                return False, f"❌ Error al procesar el identificador: {e_ident}"
            # ------------------------------------------------------------------------

            # --- PASO 4: Limpiar y preparar datos para la actualización --- 
            datos_actualizar = cotizacion_model.__dict__.copy()
            datos_actualizar.pop('escalas', None) 
            datos_actualizar.pop('id', None) 
            datos_actualizar.pop('fecha_creacion', None) 
            datos_actualizar.pop('numero_cotizacion', None) 
            datos_actualizar.pop('cliente', None) 
            datos_actualizar.pop('referencia_cliente', None)
            datos_actualizar.pop('material', None)
            datos_actualizar.pop('acabado', None)
            datos_actualizar.pop('tipo_producto', None)
    
            datos_actualizar.pop('perfil_comercial_info', None)
            datos_actualizar.pop('tipo_grafado', None) 
            # --- INICIO: QUITAR CAMPOS QUE NO PERTENECEN A 'cotizaciones' o se manejan aparte ---
            datos_actualizar.pop('valor_material', None) 
            datos_actualizar.pop('valor_plancha', None)
            datos_actualizar.pop('rentabilidad', None)
            datos_actualizar.pop('valor_acabado', None)
            datos_actualizar.pop('unidad_z_dientes', None)
            # --- FIN: QUITAR CAMPOS ---
            
            # --- INICIO: MANEJO EXPLÍCITO DE AJUSTES DE ADMIN ---
            # Usar el valor calculado en el PASO 2
            datos_actualizar['ajustes_modificados_admin'] = flag_final_ajustes_admin
            print(f"Estableciendo ajustes_modificados_admin={flag_final_ajustes_admin} en los datos de actualización")
            # --- FIN: MANEJO EXPLÍCITO DE AJUSTES DE ADMIN ---
            
            if hasattr(cotizacion_model, 'material_adhesivo_id'):
                 datos_actualizar['material_adhesivo_id'] = cotizacion_model.material_adhesivo_id
                 datos_actualizar.pop('material_id', None)
            else:
                 datos_actualizar['material_adhesivo_id'] = None
                 datos_actualizar.pop('material_id', None)

            # Convertir Decimal a float si es necesario
            if isinstance(datos_actualizar.get('valor_troquel'), Decimal):
                datos_actualizar['valor_troquel'] = float(datos_actualizar['valor_troquel'])
            if isinstance(datos_actualizar.get('valor_plancha_separado'), Decimal):
                datos_actualizar['valor_plancha_separado'] = float(datos_actualizar['valor_plancha_separado'])
            
            # --- INICIO: Incluir es_recotizacion en los datos ---
            if es_recotizacion is not None: # Añadir si se proporciona
                datos_actualizar['es_recotizacion'] = es_recotizacion
                print(f"  Añadiendo es_recotizacion={es_recotizacion} a los datos de actualización")
            # --- FIN: Incluir es_recotizacion en los datos ---

            # Convertir datetime a string ISO 8601 para serialización JSON
            if isinstance(datos_actualizar.get('ultima_modificacion_inputs'), datetime):
                datos_actualizar['ultima_modificacion_inputs'] = datos_actualizar['ultima_modificacion_inputs'].isoformat()
                
            # Añadir IDs y flags calculados
            datos_actualizar['referencia_cliente_id'] = referencia_id_final # ID de la referencia final (original o nueva)
            datos_actualizar['identificador'] = identificador_nuevo 
            
            # --- ELIMINADO: No añadir datos_calculo directamente aquí --- 

            print("\nDEBUG CotizacionManager: datos_actualizar ANTES de enviar a DBManager:")
            for k, v in datos_actualizar.items():
                print(f"  {k}: {v}")
            print(f"DEBUG CotizacionManager: Identificador específico en datos_actualizar: {datos_actualizar.get('identificador')}")
            
            # --- PASO 5: Actualizar la cotización en la BD --- 
            success_main, msg_main = self.db.actualizar_cotizacion(cotizacion_id, datos_actualizar)
            if not success_main:
                print(f"Error actualizando cotización: {msg_main}")
                return False, msg_main
                
            print("✅ Actualización principal de cotización exitosa.")
            
            # --- PASO 6: Guardar escalas actualizadas --- 
            print("\nGuardando escalas actualizadas...")
            # --- INICIO: Log detallado del contenido de escalas --- 
            if cotizacion_model.escalas:
                print(f"  Número de escalas a guardar: {len(cotizacion_model.escalas)}")
                for i, esc in enumerate(cotizacion_model.escalas):
                    print(f"    Escala {i+1}: {esc.__dict__}") # Imprimir el diccionario de la escala
            else:
                print("  cotizacion_model.escalas está vacío o es None.")
            # --- FIN: Log detallado --- 
            if cotizacion_model.escalas:
                success_scales = self.db.guardar_cotizacion_escalas(cotizacion_id, cotizacion_model.escalas)
                if not success_scales:
                    return False, "⚠️ La cotización principal se actualizó, pero hubo un error al guardar las escalas"
            else:
                print("No hay escalas para actualizar.")
                # Considerar si eliminar escalas existentes si cotizacion_model.escalas está vacío
                # self.db.eliminar_cotizacion_escalas(cotizacion_id) 
            
            # --- PASO 7: Guardar cálculos de escala actualizados --- 
            print("\nGuardando cálculos de escala actualizados...")
            # Extraer los parámetros necesarios del diccionario datos_calculo
            # Asegurarse de que las claves coincidan con las esperadas por guardar_calculos_escala
            # y proporcionar valores por defecto o manejar errores si faltan claves.
            try:
                success_calculos = self.db.guardar_calculos_escala(
                    cotizacion_id=cotizacion_id,
                    valor_material=datos_calculo.get('valor_material', 0.0),
                    valor_plancha=datos_calculo.get('valor_plancha_para_calculo', 0.0), # Usar la clave correcta
                    valor_troquel=datos_calculo.get('valor_troquel_total', 0.0), # Usar la clave correcta
                    rentabilidad=datos_calculo.get('rentabilidad', 0.0),
                    avance=datos_calculo.get('avance_calculado', cotizacion_model.avance), # Usar valor calculado o del modelo
                    ancho=datos_calculo.get('ancho_calculado', cotizacion_model.ancho),
                    existe_troquel=datos_calculo.get('existe_troquel', cotizacion_model.existe_troquel),
                    planchas_x_separado=datos_calculo.get('planchas_x_separado', cotizacion_model.planchas_x_separado),
                    num_tintas=datos_calculo.get('num_tintas', cotizacion_model.num_tintas),
                    numero_pistas=datos_calculo.get('numero_pistas', cotizacion_model.numero_pistas),
                    num_paquetes_rollos=datos_calculo.get('num_paquetes_rollos', cotizacion_model.num_paquetes_rollos),
                    tipo_producto_id=datos_calculo.get('tipo_producto_id', cotizacion_model.tipo_producto_id),
                    tipo_grafado_id=datos_calculo.get('tipo_grafado_id', cotizacion_model.tipo_grafado_id),
                    valor_acabado=datos_calculo.get('valor_acabado', 0.0),
                    unidad_z_dientes=datos_calculo.get('unidad_z_dientes', 0.0),
                    altura_grafado=datos_calculo.get('altura_grafado', cotizacion_model.altura_grafado),
                    valor_plancha_separado=datos_calculo.get('valor_plancha_separado', cotizacion_model.valor_plancha_separado),
                    parametros_especiales=datos_calculo.get('parametros_especiales')
                )
                if not success_calculos:
                    return False, "⚠️ La cotización principal y escalas se actualizaron, pero hubo un error al guardar los cálculos de escala"
            except Exception as e_calc:
                error_msg = f"❌ Error inesperado guardando cálculos de escala: {e_calc}"
                print(error_msg)
                traceback.print_exc()
                return False, error_msg

            print(f"=== Fin actualización exitosa para cotización ID: {cotizacion_id} ===")
            return True, "✅ Cotización actualizada exitosamente (incluyendo escalas y cálculos)."
                
        except ValueError as ve: # Capturar errores específicos de validación (ej: Identificador)
            print(f"Error de validación durante actualización: {ve}")
            return False, str(ve)
        except Exception as e:
            # Captura errores de los pasos 0, 1, 3 o generales
            print(f"Error general en actualizar_cotizacion_existente: {str(e)}")
            traceback.print_exc()
            return False, f"❌ Error actualizando cotización: {str(e)}"

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