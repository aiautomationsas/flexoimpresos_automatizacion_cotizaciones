from supabase import create_client, Client
from typing import List, Optional
from models import Cotizacion, Material, Acabado, Cliente, Comercial, Escala, ReferenciaCliente, TipoImpresion
import os
import logging
from dotenv import load_dotenv
from datetime import datetime
import streamlit as st

class DBManager:
    def __init__(self):
        try:
            print("\n=== INICIANDO DBMANAGER ===")
            try:
                # Intentar obtener credenciales de Streamlit primero
                print("1. Intentando obtener credenciales de Streamlit...")
                url = st.secrets["SUPABASE_URL"]
                key = st.secrets["SUPABASE_KEY"]
                print("Credenciales de Streamlit obtenidas correctamente")
            except Exception as e:
                print(f"No se pudieron obtener credenciales de Streamlit: {e}")
                print("2. Intentando obtener credenciales de variables de entorno...")
                # Si no está en Streamlit, usar variables de entorno
                load_dotenv()
                url = os.getenv("SUPABASE_URL")
                key = os.getenv("SUPABASE_KEY")
                print("Credenciales de variables de entorno obtenidas")
            
            if not url or not key:
                raise ValueError("SUPABASE_URL y SUPABASE_KEY deben estar definidas")
            
            print(f"3. URL de Supabase: {url[:30]}...")  # Solo mostramos el inicio de la URL por seguridad
            print(f"4. Key length: {len(key) if key else 0} caracteres")
            
            print("5. Intentando crear cliente Supabase...")
            self.client = create_client(url, key)
            print("6. Cliente Supabase creado correctamente")
            
            # Verificar la tabla clientes
            if not self.verificar_tabla_clientes():
                raise Exception("No se pudo verificar la tabla clientes")
            
            print("=== DBMANAGER INICIADO CORRECTAMENTE ===\n")
            
        except Exception as e:
            print("\n!!! ERROR AL INICIAR DBMANAGER !!!")
            print(f"Tipo de error: {type(e)}")
            print(f"Mensaje de error: {str(e)}")
            print("\nStack trace completo:")
            import traceback
            traceback.print_exc()
            raise

    def get_materiales(self) -> List[Material]:
        try:
            response = self.client.table('materiales').select('*').execute()
            if not response.data:
                logging.warning("No se encontraron materiales")
            return [Material(**item) for item in response.data]
        except Exception as e:
            logging.error(f"Error al obtener materiales: {str(e)}")
            raise

    def get_acabados(self) -> List[Acabado]:
        try:
            response = self.client.table('acabados').select('*').execute()
            if not response.data:
                logging.warning("No se encontraron acabados")
            return [Acabado(**item) for item in response.data]
        except Exception as e:
            logging.error(f"Error al obtener acabados: {str(e)}")
            raise

    def get_comerciales(self) -> List[Comercial]:
        response = self.client.table('comerciales').select('*').execute()
        return [Comercial(**item) for item in response.data]

    def get_clientes(self) -> List[Cliente]:
        try:
            print("\n=== INICIO GET_CLIENTES ===")
            print("Intentando obtener clientes usando RPC...")
            
            # Llamar a RPC para obtener clientes
            response = self.client.rpc(
                'obtener_clientes'
            ).execute()
            
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
        
        except Exception as e:
            print(f"Error al obtener clientes: {e}")
            import traceback
            traceback.print_exc()
            raise

    def _limpiar_datos(self, data: dict) -> dict:
        """
        Limpia los datos antes de enviarlos a la base de datos:
        - Elimina campos None
        - Elimina campos de fecha manejados por la BD
        """
        campos_fecha = ['creado_en', 'actualizado_en', 'created_at', 'updated_at']
        return {
            k: v for k, v in data.items() 
            if v is not None and k not in campos_fecha
        }

    def crear_cliente(self, cliente: Cliente) -> Cliente:
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
                response = self.client.rpc(
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
                verify = self.client.table('clientes').select('*').eq('id', nuevo_cliente.id).execute()
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
                import traceback
                traceback.print_exc()
                raise Exception(f"Error al crear cliente: {str(e)}")
        
        except Exception as e:
            print("\n!!! ERROR GENERAL EN CREAR_CLIENTE !!!")
            print(f"Tipo de error: {type(e)}")
            print(f"Mensaje de error: {str(e)}")
            print("\nStack trace completo:")
            import traceback
            traceback.print_exc()
            raise

    def get_referencias_cliente(self, cliente_id: int) -> List[ReferenciaCliente]:
        try:
            print(f"\n=== INICIO GET_REFERENCIAS_CLIENTE para cliente_id={cliente_id} ===")
            
            # Llamar a RPC para obtener referencias
            response = self.client.rpc(
                'obtener_referencias_cliente',
                {'p_cliente_id': cliente_id}
            ).execute()
            
            print("Respuesta de get_referencias_cliente:")
            print("Tipo de respuesta:", type(response))
            print("Datos en la respuesta:", response.data if hasattr(response, 'data') else None)
            
            if not response.data:
                print("No se encontraron referencias para este cliente")
                return []
            
            referencias = [ReferenciaCliente(**item) for item in response.data]
            print(f"Número de referencias encontradas: {len(referencias)}")
            print("=== FIN GET_REFERENCIAS_CLIENTE ===\n")
            return referencias
            
        except Exception as e:
            print(f"Error al obtener referencias del cliente: {e}")
            import traceback
            traceback.print_exc()
            raise

    def crear_referencia(self, referencia: ReferenciaCliente) -> ReferenciaCliente:
        try:
            print("\n=== INICIO CREAR REFERENCIA ===")
            
            # Preparar datos RPC
            rpc_data = {
                'p_cliente_id': referencia.cliente_id,
                'p_codigo_referencia': referencia.codigo_referencia,
                'p_descripcion': referencia.descripcion,
                'p_tipo_impresion_id': referencia.tipo_impresion_id
            }
            
            print("Datos RPC preparados:")
            for k, v in rpc_data.items():
                print(f"  {k}: {v}")
            
            # Llamar a RPC
            response = self.client.rpc('insertar_referencia', rpc_data).execute()
            
            print("\nRespuesta RPC recibida:")
            print(f"Tipo de respuesta: {type(response)}")
            print(f"Datos en response: {response.data if hasattr(response, 'data') else 'Sin datos'}")
            
            if not response.data:
                raise Exception("No se pudo crear la referencia. Respuesta vacía.")
            
            # Crear y retornar objeto ReferenciaCliente
            nueva_referencia = ReferenciaCliente(**response.data[0])
            print(f"Referencia creada exitosamente: {nueva_referencia}")
            
            return nueva_referencia
            
        except Exception as e:
            print(f"Error al crear referencia: {e}")
            import traceback
            traceback.print_exc()
            raise

    def crear_cotizacion(self, cotizacion: Cotizacion) -> Cotizacion:
        # Primero insertamos la cotización
        cotizacion_data = self._limpiar_datos({
            k: v for k, v in cotizacion.__dict__.items() 
            if k != 'escalas'
        })
        
        response = self.client.table('cotizaciones').insert(cotizacion_data).execute()
        if not response.data:
            raise Exception("Error al crear la cotización")
        
        cotizacion_id = response.data[0]['id']
        
        # Luego insertamos las escalas
        for escala in cotizacion.escalas:
            escala.cotizacion_id = cotizacion_id
            escala_data = self._limpiar_datos(escala.__dict__)
            self.client.table('escalas').insert(escala_data).execute()
        
        return self.get_cotizacion(cotizacion_id)

    def get_cotizacion(self, cotizacion_id: int) -> Optional[Cotizacion]:
        # Obtener la cotización
        response = self.client.table('cotizaciones').select('*').eq('id', cotizacion_id).execute()
        if not response.data:
            return None
            
        cotizacion_data = response.data[0]
        
        # Obtener las escalas asociadas
        escalas_response = self.client.table('escalas').select('*').eq('cotizacion_id', cotizacion_id).execute()
        escalas = [Escala(**item) for item in escalas_response.data]
        
        cotizacion_data['escalas'] = escalas
        return Cotizacion(**cotizacion_data)

    def get_tipos_impresion(self) -> List[TipoImpresion]:
        response = self.client.table('tipo_impresion').select('*').execute()
        return [TipoImpresion(**item) for item in response.data]

    def crear_cliente_prueba(self):
        try:
            # Datos de cliente de prueba
            cliente_data = self._limpiar_datos({
                'nombre': 'Cliente de Prueba',
                'codigo': 'TEST001',
                'persona_contacto': 'Juan Pérez',
                'correo_electronico': 'juan.perez@ejemplo.com',
                'telefono': '+573001234567'
            })
            
            print("Intentando insertar cliente de prueba:")
            print("Datos:", cliente_data)
            
            # Insertar cliente de prueba
            response = (
                self.client.table('clientes')
                .insert(cliente_data)
                .execute()
            )
            
            # Verificar respuesta
            print("Respuesta de inserción de prueba:")
            print("Tipo de respuesta:", type(response))
            print("Datos en la respuesta:", response.data)
            
            if not response.data:
                raise Exception("No se pudo insertar el cliente de prueba. Respuesta vacía.")
            
            return response.data[0]
        
        except Exception as e:
            print(f"Error al insertar cliente de prueba: {e}")
            # Imprimir traza del error
            import traceback
            traceback.print_exc()
            raise

    def verificar_estructura_tabla(self):
        try:
            # Intentar obtener información de la tabla
            print("Verificando estructura de la tabla clientes...")
            
            # Consultar información de columnas
            query = """
            SELECT column_name, data_type, character_maximum_length
            FROM information_schema.columns
            WHERE table_name = 'clientes';
            """
            
            response = self.client.rpc('execute_sql', {'query': query}).execute()
            
            print("Estructura de la tabla clientes:")
            for columna in response.data:
                print(columna)
        
        except Exception as e:
            print(f"Error al verificar estructura de la tabla: {e}")
            import traceback
            traceback.print_exc()

    def verificar_permisos(self):
        try:
            print("Verificando permisos de la tabla clientes...")
            
            # Intentar realizar operaciones básicas
            print("1. Intentando SELECT:")
            select_response = self.client.table('clientes').select('*').execute()
            print("SELECT exitoso")
            
            print("2. Intentando INSERT:")
            # Generar un código único usando timestamp
            codigo_unico = f"TEST_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            
            insert_data = {
                'nombre': 'Test Permisos',
                'codigo': codigo_unico,
                'persona_contacto': 'Verificador Permisos'
            }
            insert_response = self.client.table('clientes').insert(insert_data).execute()
            print("INSERT exitoso")
            
            # Opcional: Eliminar el cliente de prueba
            if insert_response.data:
                self.client.table('clientes').delete().eq('id', insert_response.data[0]['id']).execute()
                print("Cliente de prueba eliminado")
            
            print("3. Verificando políticas de RLS:")
            print("Todos los permisos verificados correctamente")
        
        except Exception as e:
            print(f"Error de permisos: {e}")
            import traceback
            traceback.print_exc()
            raise 

    def verificar_tabla_clientes(self):
        try:
            print("\n=== VERIFICANDO TABLA CLIENTES ===")
            print("1. Intentando conexión inicial...")
            
            # Verificar si la tabla existe
            response = self.client.table('clientes').select('count').execute()
            print("2. Respuesta de count:", response.data if hasattr(response, 'data') else "Sin datos")
            
            # Obtener estructura de la tabla
            print("3. Intentando obtener estructura...")
            response = self.client.from_('clientes').select('*').limit(1).execute()
            
            if response.data:
                print("4. Estructura de un registro:", response.data[0].keys())
            else:
                print("4. Tabla vacía pero accesible")
            
            print("=== VERIFICACIÓN COMPLETADA CON ÉXITO ===\n")
            return True
            
        except Exception as e:
            print("\n!!! ERROR EN VERIFICACIÓN DE TABLA CLIENTES !!!")
            print(f"Tipo de error: {type(e)}")
            print(f"Mensaje de error: {str(e)}")
            print("\nStack trace completo:")
            import traceback
            traceback.print_exc()
            
            # Verificar si es un error de autenticación
            if "JWT" in str(e) or "authentication" in str(e).lower():
                print("\nPosible problema de autenticación:")
                print("- Verifica que la SUPABASE_KEY sea correcta")
                print("- Asegúrate de usar la 'anon key' o 'service_role key' correcta")
            
            # Verificar si es un error de conexión
            if "connection" in str(e).lower():
                print("\nPosible problema de conexión:")
                print("- Verifica que la SUPABASE_URL sea correcta")
                print("- Comprueba tu conexión a internet")
            
            return False

    def verificar_funcion_rpc(self):
        try:
            print("\n=== VERIFICANDO FUNCIÓN RPC ===")
            # Intentar llamar directamente a la función con datos de prueba
            test_data = {
                'p_nombre': 'Test RPC',
                'p_codigo': f'TEST_{datetime.now().strftime("%Y%m%d_%H%M%S")}',
                'p_persona_contacto': 'Test Contact'
            }
            
            print("Intentando llamada de prueba a RPC...")
            response = self.client.rpc('insertar_cliente', test_data).execute()
            
            print("Respuesta de prueba RPC:", response.data if hasattr(response, 'data') else response)
            
            # Si llegamos aquí, la función existe y funciona
            if hasattr(response, 'data') and response.data:
                print("Función RPC verificada y funcionando")
                # Limpiar el cliente de prueba
                if response.data[0].get('id'):
                    self.client.table('clientes').delete().eq('id', response.data[0]['id']).execute()
                    print("Cliente de prueba eliminado")
                return True
            else:
                print("La función existe pero no retorna datos")
                return False
            
        except Exception as e:
            print(f"Error al verificar función RPC: {e}")
            print("Detalles del error:", str(e))
            return False 

    def get_material_code(self, material_id: int) -> str:
        """Obtiene el código del material por su ID"""
        try:
            response = self.client.table('materiales').select('code').eq('id', material_id).execute()
            if response.data and len(response.data) > 0:
                return response.data[0]['code']
            return ""
        except Exception as e:
            print(f"Error al obtener código de material: {e}")
            return ""

    def get_acabado_code(self, acabado_id: int) -> str:
        """Obtiene el código del acabado por su ID"""
        try:
            response = self.client.table('acabados').select('code').eq('id', acabado_id).execute()
            if response.data and len(response.data) > 0:
                return response.data[0]['code']
            return ""
        except Exception as e:
            print(f"Error al obtener código de acabado: {e}")
            return "" 