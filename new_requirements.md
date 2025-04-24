Trigger para verificar:
CREATE OR REPLACE FUNCTION validar_id_motivo_rechazo()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.estado_id = 3 AND NEW.id_motivo_rechazo IS NULL THEN
        RAISE EXCEPTION 'id_motivo_rechazo no puede ser NULL cuando estado_id es 3';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER check_id_motivo_rechazo
BEFORE INSERT OR UPDATE ON public.cotizaciones
FOR EACH ROW EXECUTE FUNCTION validar_id_motivo_rechazo();