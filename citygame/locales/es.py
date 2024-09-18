# locales/es.py

translations = {
    # General
    "help_title": "Ayuda de Ciudad Virtual",
    "help_text": (
        "Bienvenido a **Ciudad Virtual**. Aquí puedes elegir entre ser mafia, "
        "civil o policía y participar en diversas actividades.\n\n"
        "**Comandos Disponibles:**\n"
        "`!juego establecer_idioma <es/en>` - Establece tu idioma preferido.\n"
        "`!juego elegir_rol <rol>` - Elige tu rol en el juego.\n"
        "`!juego accion` - Realiza una acción según tu rol.\n"
        "`!juego trabajar` - Trabaja para ganar monedas.\n"
        "`!juego mision_diaria` - Obtén tu misión diaria.\n"
        "`!juego logros` - Muestra tus logros.\n"
        "`!juego clasificacion` - Muestra la clasificación de jugadores.\n"
        "`!juego desafiar @usuario` - Desafía a otro jugador.\n"
        "`!juego comprar <objeto>` - Compra un objeto de la tienda.\n"
        "`!juego inventario` - Muestra tu inventario."
    ),
    "language_set": "Tu idioma ha sido establecido a '{language}'.",
    "no_role": (
        "No has elegido un rol. Por favor, elige un rol usando "
        "`!juego elegir_rol <rol>`."
    ),
    "role_invalid": (
        "El rol ingresado no es válido. Los roles disponibles son "
        "mafia, civil y policía."
    ),
    "role_selected": "Has elegido el rol de **{role}**.",
    "no_achievements": "Aún no has obtenido ningún logro.",
    "achievements_title": "Tus Logros",
    "inventory_empty": "Tu inventario está vacío.",
    "inventory_title": "Tu Inventario",
    "no_leaderboard_data": "No hay datos suficientes para mostrar la clasificación.",
    "leaderboard_title": "Clasificación de Jugadores",
    "item_not_found": "El objeto especificado no existe en la tienda.",
    "not_enough_money": "No tienes suficientes monedas para comprar este objeto.",
    "item_purchased": "Has comprado **{item}** exitosamente.",
    "daily_mission_completed": "Ya has completado tu misión diaria.",
    "daily_mission_in_progress": (
        "Ya tienes una misión diaria en progreso: **{mission}**."
    ),
    "daily_mission_assigned": (
        "Se te ha asignado una nueva misión diaria: **{mission}**."
    ),
    "level_up_title": "¡Nivel Superior!",
    "level_up": "¡Felicidades! Has alcanzado el nivel {level}.",
    "released_title": "Has sido liberado",
    "released_from_jail": (
        "Has cumplido tu tiempo en la cárcel y ahora eres libre."
    ),
    "in_jail_title": "Estás en la cárcel",
    "in_jail": (
        "Debes esperar {time} minutos antes de poder realizar esta acción."
    ),
    "caught_title": "¡Te Han Capturado!",
    "caught_by_police": (
        "La policía te ha capturado durante tus actividades ilegales. "
        "Estarás en la cárcel por 3 minutos."
    ),
    "action_title": "Acción",
    "action_mafia": (
        "Has realizado una operación clandestina y ganado {earnings} monedas "
        "y {xp_gain} puntos de experiencia."
    ),
    "action_civilian": (
        "Has trabajado honestamente y ganado {earnings} monedas "
        "y {xp_gain} puntos de experiencia."
    ),
    "action_police": (
        "Has patrullado la ciudad y ganado {earnings} monedas "
        "y {xp_gain} puntos de experiencia."
    ),
    "work_title": "Trabajo",
    "work_success": (
        "Has completado tu trabajo y ganado {earnings} monedas "
        "y {xp_gain} puntos de experiencia."
    ),
    "challenge_result": "¡{winner} ha ganado el desafío!",
    # Misiones Diarias
    "daily_missions": [
        "Capturar a 5 miembros de la mafia.",
        "Completar 3 trabajos exitosamente.",
        "Ganar un total de 1000 monedas.",
        "Alcanzar el nivel 5.",
        "Realizar 10 acciones.",
        "Desafiar y ganar contra otro jugador.",
    ],
}

