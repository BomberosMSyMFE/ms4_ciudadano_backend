class DominioCiudadanoException(Exception):
    pass

class CoordenadasInvalidasException(DominioCiudadanoException):
    def __init__(self, lat: float, lon: float):
        super().__init__(f"Coordenadas fuera de rango: lat={lat}, lon={lon}")

class DescripcionVaciaException(DominioCiudadanoException):
    def __init__(self):
        super().__init__("La descripcion del incidente no puede estar vacia")

class TicketNoEncontradoException(DominioCiudadanoException):
    def __init__(self, ticket_id: str):
        super().__init__(f"Denuncia no encontrada con radicado: {ticket_id}")
