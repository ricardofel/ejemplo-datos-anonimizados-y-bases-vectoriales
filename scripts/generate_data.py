"""Genera data/tickets_sinteticos.csv con tickets 100% sinteticos.

Todo es inventado: nombres, cedulas (con digito verificador valido),
correos (dominios reservados example.com/.org/.net y .example) y
telefonos aleatorios. Cualquier coincidencia con una persona real es
accidental. La semilla es fija, asi que el CSV es reproducible.

Uso (PowerShell):
    python scripts/generate_data.py
"""

from __future__ import annotations

import csv
import random
import sys
import unicodedata
from datetime import date, timedelta
from pathlib import Path

SEED = 2026
OUTPUT = Path(__file__).resolve().parent.parent / "data" / "tickets_sinteticos.csv"

FIRST_NAMES = [
    "María Fernanda", "José Luis", "Ana Belén", "Carlos", "Daniela", "Andrés",
    "Gabriela", "Juan Pablo", "Valeria", "Diego", "Paola", "Luis Miguel",
    "Camila", "Santiago", "Verónica", "Fernando", "Karina", "Mateo",
    "Lucía", "Esteban", "Mónica", "Sebastián", "Patricia", "Javier",
    "Doménica", "Ricardo", "Estefanía", "Byron", "Cristina", "Wilson",
]
LAST_NAMES = [
    "Andrade", "Benítez", "Cevallos", "Delgado", "Espinoza", "Flores",
    "Guerrero", "Herrera", "Jaramillo", "León", "Mendoza", "Naranjo",
    "Ordóñez", "Paredes", "Quishpe", "Romero", "Salazar", "Torres",
    "Vásquez", "Yánez", "Zambrano", "Cabrera", "Moreno", "Ruiz",
    "Villacís", "Guamán", "Chávez", "Ortiz", "Pazmiño", "Tapia",
]
EMAIL_DOMAINS = ["example.com", "example.org", "example.net", "correo.example"]
CAREERS = [
    "Ingeniería Civil", "Contabilidad", "Medicina", "Derecho", "Arquitectura",
    "Psicología", "Ingeniería de Software", "Administración de Empresas",
]

# Cada escenario: categoria, resolucion y 3 redacciones distintas del mismo
# problema. Las redacciones usan vocabulario diferente a proposito para que
# la busqueda por palabras clave falle y la semantica se luzca.
SCENARIOS = [
    # ---------------- acceso/contraseña ----------------
    ("acceso/contraseña",
     "Se desbloqueó la cuenta desde la consola de identidad y se pidió al usuario restablecer la contraseña con el enlace de autoservicio.",
     ["Intenté ingresar varias veces al portal y ahora me aparece que mi cuenta está bloqueada.",
      "No puedo entrar a mi cuenta, puse mal la clave tres veces y el sistema me sacó.",
      "Se me bloqueó el acceso después de equivocarme con la contraseña, ¿me pueden ayudar a desbloquearlo?"]),
    ("acceso/contraseña",
     "El correo alterno estaba desactualizado; se actualizó y se reenvió el enlace de recuperación.",
     ["Olvidé mi contraseña y el correo de recuperación nunca me llega.",
      "Pedí restablecer la clave pero no recibo el mensaje con el enlace, ni siquiera en spam.",
      "El botón de olvidé mi contraseña no me envía nada, ya esperé una hora."]),
    ("acceso/contraseña",
     "Se validó la identidad por videollamada, se reinició el segundo factor y el usuario lo registró en su nuevo dispositivo.",
     ["Cambié de celular y ya no me llega el código de verificación para iniciar sesión.",
      "El segundo factor de autenticación me pide un código que no recibo por SMS.",
      "Perdí el teléfono donde tenía la app autenticadora y no puedo completar el login."]),
    ("acceso/contraseña",
     "Se explicó la política de contraseñas (12 caracteres, mayúscula, número y símbolo, sin repetir las últimas 5) y el usuario logró cambiarla.",
     ["El sistema dice que mi contraseña expiró y no me deja ponerle una nueva.",
      "Me pide cambiar la clave pero todas las que pongo dicen que no cumplen la política.",
      "Mi clave caducó y al intentar renovarla me sale un error de requisitos."]),
    ("acceso/contraseña",
     "La cuenta estaba pendiente de sincronización con el sistema académico; se forzó la sincronización y quedó activa en 15 minutos.",
     ["Soy estudiante nuevo y mi usuario institucional todavía no funciona.",
      "Me dieron credenciales al inscribirme pero el portal dice que el usuario no existe.",
      "Recién me matriculé y no puedo activar mi cuenta del campus virtual."]),
    # ---------------- pagos ----------------
    ("pagos",
     "El banco emisor bloqueaba compras en línea; se recomendó habilitarlas o pagar por transferencia y el pago se completó.",
     ["Intento pagar la matrícula con mi tarjeta de crédito y la pasarela me lo rechaza.",
      "La página de pagos no acepta mi tarjeta, dice transacción declinada.",
      "Quise cancelar la pensión en línea pero el cobro con tarjeta no pasa."]),
    ("pagos",
     "Se confirmó el doble débito con la pasarela y se gestionó el reverso del cobro duplicado en 5 días hábiles.",
     ["Me debitaron dos veces el mismo valor de la pensión.",
      "En mi estado de cuenta aparece el cobro de la matrícula repetido.",
      "Pagué una sola vez pero el banco me descontó el doble."]),
    ("pagos",
     "Se concilió el pago con el comprobante enviado y se registró manualmente; la deuda quedó en cero.",
     ["Ya pagué por transferencia hace tres días y en el sistema sigo apareciendo con deuda.",
      "Hice el depósito pero mi pago no se refleja y no me dejan inscribirme.",
      "El portal todavía muestra saldo pendiente aunque ya cancelé todo."]),
    ("pagos",
     "Se registró la solicitud de reembolso con el formulario financiero; el valor se acredita en 15 días hábiles.",
     ["Me retiré de una materia y quiero que me devuelvan lo que pagué.",
      "Necesito un reembolso porque anulé mi inscripción a tiempo.",
      "¿Cómo pido la devolución del dinero de un curso que no voy a tomar?"]),
    ("pagos",
     "Se explicó el plan de pagos en hasta 6 cuotas sin intereses y se generó el convenio firmado electrónicamente.",
     ["Quisiera pagar la colegiatura en cuotas porque no me alcanza para el valor completo.",
      "¿Existe la opción de diferir la pensión a varios meses?",
      "Necesito un convenio de pago para la deuda del semestre."]),
    # ---------------- facturación ----------------
    ("facturación",
     "Se anuló la factura con nota de crédito y se emitió una nueva con los datos tributarios correctos.",
     ["La factura salió con un RUC equivocado y la necesito para mi empresa.",
      "Mi factura tiene mal los datos del cliente, deben corregirla.",
      "Emitieron el comprobante a nombre de otra razón social."]),
    ("facturación",
     "La factura estaba autorizada por el SRI pero el envío falló; se reenvió y se indicó cómo descargarla desde el portal.",
     ["Pagué hace una semana y nunca me llegó la factura electrónica.",
      "No recibo el comprobante electrónico en mi bandeja de entrada.",
      "¿Dónde puedo descargar la factura de mi pago? No me la enviaron."]),
    ("facturación",
     "Se registró al tercero como responsable de pago con su RUC; las próximas facturas se emiten a su nombre.",
     ["Mi empresa me paga la maestría y necesita que la factura salga a su nombre.",
      "Quiero que facturen a nombre de mi papá porque él paga la carrera.",
      "¿Se puede emitir la factura a otra persona distinta del estudiante?"]),
    ("facturación",
     "La diferencia correspondía a la comisión de la pasarela; se explicó el desglose y se emitió el detalle corregido.",
     ["El valor de la factura no coincide con lo que pagué.",
      "Me facturaron un monto mayor al que aparece en mi comprobante de pago.",
      "Hay una diferencia entre el total facturado y lo que realmente se debitó."]),
    ("facturación",
     "Se emitió la nota de crédito para la factura duplicada y se notificó al SRI.",
     ["Necesito que anulen una factura que salió duplicada.",
      "Me emitieron dos facturas por el mismo pago, ¿pueden dar de baja una?",
      "Solicito una nota de crédito por una factura generada por error."]),
    # ---------------- app móvil ----------------
    ("app móvil",
     "Se pidió actualizar la app a la última versión y borrar la caché; el error era conocido en la versión anterior.",
     ["La aplicación del celular se cierra apenas la abro.",
      "La app se crashea en mi Android cuando intento entrar.",
      "Cada vez que abro la app móvil se queda en blanco y se cierra sola."]),
    ("app móvil",
     "Las notificaciones estaban bloqueadas por el ahorro de batería del teléfono; se activaron los permisos y comenzaron a llegar.",
     ["No me llegan las notificaciones de la app sobre mis notas.",
      "La aplicación ya no me avisa cuando publican calificaciones.",
      "Dejé de recibir alertas push en el teléfono."]),
    ("app móvil",
     "La app guardaba un token antiguo; se cerró sesión, se reinstaló y el usuario pudo ingresar.",
     ["En la página web entro normal, pero en la app me dice credenciales inválidas.",
      "La app móvil no acepta mi usuario aunque en la computadora sí funciona.",
      "Solo en el celular me sale error de inicio de sesión."]),
    ("app móvil",
     "Se indicó la versión mínima soportada (Android 9 o iOS 15) y el acceso alternativo por la web móvil.",
     ["No encuentro la app en la tienda de mi teléfono Huawei.",
      "Mi celular es antiguo y dice que la aplicación no es compatible.",
      "¿Hay versión de la app para iPhone? Solo veo la de Android."]),
    ("app móvil",
     "El servicio de carnet digital tuvo una caída; se restableció y se pidió refrescar la app.",
     ["El carnet digital no carga en la app y lo necesito para entrar al campus.",
      "La sección de horario en la aplicación aparece vacía.",
      "La credencial virtual del estudiante se queda cargando."]),
    # ---------------- matrícula/académico ----------------
    ("matrícula/académico",
     "Se abrió un paralelo adicional y se inscribió al estudiante en la lista de espera con prioridad.",
     ["No puedo inscribirme en Cálculo II porque dice que no hay cupos.",
      "La materia que necesito aparece llena y no me deja matricularme.",
      "Quiero tomar una asignatura pero el sistema me indica cupo agotado."]),
    ("matrícula/académico",
     "La nota del prerrequisito no estaba cerrada en el sistema; secretaría la cerró y se habilitó la inscripción.",
     ["El sistema no me deja tomar una materia porque dice que me falta un prerrequisito que ya aprobé.",
      "Ya aprobé Programación I pero no me habilita Programación II.",
      "Me bloquea la inscripción por un requisito que sí cumplí el semestre pasado."]),
    ("matrícula/académico",
     "Se derivó al docente, quien corrigió la nota en el sistema dentro del plazo de recalificación.",
     ["Mi calificación del examen final está mal registrada.",
      "En el sistema me aparece una nota menor a la que el profesor me dio.",
      "Quiero solicitar recalificación porque creo que hubo un error en mi nota."]),
    ("matrícula/académico",
     "Se indicó que el certificado se descarga firmado electrónicamente desde el portal, sección Trámites.",
     ["Necesito un certificado de matrícula para presentarlo en el IESS.",
      "¿Cómo obtengo una constancia de que soy estudiante regular?",
      "Me piden un documento que certifique que estoy matriculado este semestre."]),
    ("matrícula/académico",
     "Se explicó el retiro voluntario en el portal hasta la semana 6 sin afectar el récord académico.",
     ["Quiero retirarme de una asignatura antes de que termine el plazo.",
      "¿Cuál es el procedimiento para dar de baja una materia?",
      "Necesito anular mi inscripción en Física porque se cruza con mi trabajo."]),
    # ---------------- soporte técnico ----------------
    ("soporte técnico",
     "Se configuró el perfil WPA2-Enterprise con el certificado institucional y la conexión funcionó.",
     ["No me puedo conectar al wifi de la universidad desde mi laptop.",
      "La red inalámbrica del campus me rechaza la conexión.",
      "En la biblioteca el internet inalámbrico no funciona en mi computadora."]),
    ("soporte técnico",
     "Se amplió la cuota del buzón y se explicó cómo archivar mensajes antiguos.",
     ["Mi correo institucional dice que el buzón está lleno y no recibo mensajes.",
      "No puedo enviar correos desde la cuenta de la universidad.",
      "El email institucional rebota todo lo que me mandan."]),
    ("soporte técnico",
     "Se asignó la licencia desde el portal de software y se enviaron las instrucciones de instalación.",
     ["Necesito activar la licencia de Office que da la universidad.",
      "¿Cómo instalo Matlab con la licencia de estudiante?",
      "El software académico me dice que la licencia expiró."]),
    ("soporte técnico",
     "El archivo superaba el límite de 50 MB; se indicó comprimirlo y el docente amplió el plazo de entrega.",
     ["No puedo subir mi tarea al aula virtual, da error al cargar el archivo.",
      "La plataforma de clases no me deja adjuntar el trabajo.",
      "Al entregar la tarea en el campus virtual la página se queda pegada."]),
    ("soporte técnico",
     "Se reemplazó el switch averiado del laboratorio y se restableció la conectividad.",
     ["En el laboratorio de cómputo las máquinas no tienen internet.",
      "Las computadoras del laboratorio 3 no se conectan a la red.",
      "Ningún equipo de la sala de informática puede navegar."]),
]

OPENINGS = [
    "Buenos días, mi nombre es {name}.",
    "Hola, les escribe {name}.",
    "Saludos, soy {name}, estudiante de {career}.",
    "Estimados, mi nombre es {name} y tengo un inconveniente.",
    "Buenas tardes. Soy {name}.",
]
CONTACTS = [
    "Mi cédula es {cedula}, mi correo {email} y mi celular {phone}.",
    "Datos: C.I. {cedula}, teléfono {phone}, email {email}.",
    "Pueden contactarme al {phone} o a {email}. Cédula: {cedula}.",
    "Adjunto mis datos: cédula {cedula}, correo {email}, número {phone}.",
    "Gracias de antemano. {name}, CI {cedula}, {email}, {phone}.",
]

# Casos dificiles a proposito, para discutir los limites del enmascarado.
# Se aplican sobre tickets concretos (por indice de escenario y variante).
HARD_CASES = {
    # (indice_escenario, indice_variante): plantilla
    (0, 1): "hola soy {lower_name}, {problem_lower} mi cedula es {cedula} y mi numero {phone}",
    (20, 0): "Qué tal, habla Panchito, el delegado del curso de Contabilidad. {problem} Mi celu es {phone}.",
    (22, 2): "Les escribe el decano de la Facultad de Ingeniería de la sede Loja. {problem} Contacto: {email}.",
    (11, 0): "Buenas, soy {name}. {problem} Mi correo es {email_local} arroba example punto com, cédula {cedula}.",
}


def ascii_fold(text: str) -> str:
    """Quita tildes y enies para construir la parte local del correo."""
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(c for c in normalized if not unicodedata.combining(c))


def cedula_check_digit(first_nine: str) -> int:
    """Digito verificador de la cedula ecuatoriana (modulo 10)."""
    total = 0
    for i, ch in enumerate(first_nine):
        value = int(ch) * (2 if i % 2 == 0 else 1)
        total += value - 9 if value > 9 else value
    return (10 - total % 10) % 10


def fake_cedula(rng: random.Random) -> str:
    province = rng.randint(1, 24)
    third = rng.randint(0, 5)  # persona natural
    rest = "".join(str(rng.randint(0, 9)) for _ in range(6))
    first_nine = f"{province:02d}{third}{rest}"
    return first_nine + str(cedula_check_digit(first_nine))


def fake_phone(rng: random.Random) -> str:
    # Celulares 096-099: nunca coinciden con una cedula valida (tercer digito > 5)
    digits = "09" + rng.choice("6789") + "".join(str(rng.randint(0, 9)) for _ in range(7))
    style = rng.randint(0, 4)
    if style == 0:
        return digits
    if style == 1:
        return f"{digits[:3]} {digits[3:6]} {digits[6:]}"
    if style == 2:
        return f"{digits[:3]}-{digits[3:6]}-{digits[6:]}"
    if style == 3:
        return "+593" + digits[1:]
    return f"+593 {digits[1:3]} {digits[3:6]} {digits[6:]}"


def fake_person(rng: random.Random) -> tuple[str, str]:
    first = rng.choice(FIRST_NAMES)
    last1, last2 = rng.sample(LAST_NAMES, 2)
    name = f"{first} {last1} {last2}"
    local = ascii_fold(f"{first.split()[0]}.{last1}").lower() + str(rng.randint(1, 99))
    return name, local


def random_date(rng: random.Random) -> str:
    start = date(2026, 1, 5)
    return (start + timedelta(days=rng.randint(0, 290))).isoformat()


def build_rows(seed: int = SEED) -> list[dict]:
    rng = random.Random(seed)
    rows = []
    for s_idx, (category, resolution, variants) in enumerate(SCENARIOS):
        for v_idx, problem in enumerate(variants):
            name, local = fake_person(rng)
            email = f"{local}@{rng.choice(EMAIL_DOMAINS)}"
            values = {
                "name": name,
                "lower_name": name.lower(),
                "career": rng.choice(CAREERS),
                "cedula": fake_cedula(rng),
                "email": email,
                "email_local": local,
                "phone": fake_phone(rng),
                "problem": problem,
                "problem_lower": problem[0].lower() + problem[1:],
            }
            hard = HARD_CASES.get((s_idx, v_idx))
            if hard:
                text = hard.format(**values)
            else:
                opening = rng.choice(OPENINGS).format(**values)
                contact = rng.choice(CONTACTS).format(**values)
                text = f"{opening} {problem} {contact}"
            rows.append({
                "fecha": random_date(rng),
                "categoria": category,
                "texto": text,
                "resolucion": resolution,
            })
    rng.shuffle(rows)
    for i, row in enumerate(rows, start=1):
        row["id"] = f"TCK-{i:04d}"
    return rows


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    rows = build_rows()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["id", "fecha", "categoria", "texto", "resolucion"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"Se generaron {len(rows)} tickets sintéticos en {OUTPUT}")


if __name__ == "__main__":
    main()
